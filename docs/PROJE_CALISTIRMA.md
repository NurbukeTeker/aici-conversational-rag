# Proje Nasıl Çalışıyor & Sıfırdan Çalıştırma

## 1. Genel akış (ne nasıl çalışıyor?)

```
Frontend (3000) → Backend (8000) → Agent (8001)
                      ↓                    ↓
                   Redis              ChromaDB
                   SQLite             (PDF chunks)
```

- **Frontend:** Kullanıcı girişi, JSON editörü, soru + cevap/evidence gösterimi.
- **Backend:** Auth (JWT), session (Redis), her Q&A’da en güncel `session_objects`’ı alıp Agent’a gönderir.
- **Agent:** Sadece `{ question, session_objects }` alır (stateless). LangGraph ile: smalltalk/geometry guard → retrieve (Chroma) → doc-only veya hybrid chain (LLM) → evidence → cevap döner.

---

## 2. LangGraph nasıl çalışıyor?

Agent içinde tek “motor” **LangGraph** StateGraph:

1. **validate** → session JSON uyarıları (opsiyonel)
2. **smalltalk** → “Merhaba” vb. ise RAG/LLM yok, sabit cevap
3. **geometry_guard** → “Ön cephe highway’e bakıyor mu?” gibi sorularda geometry yoksa LLM’e sormadan sabit “Cannot determine…” mesajı
4. **followup** → “Eksik ne?” gibi sorularda sabit checklist
5. **summarize** → `ReasoningService` ile session summary (layer sayıları, plot boundary var mı vb.)
6. **retrieve** → `retrieval_lc.retrieve()` ile Chroma’dan ilgili chunk’lar
7. **route** → Soru “tanım” tipindeyse doc-only, değilse hybrid
8. **llm** → LCEL chain (doc_only_chain veya hybrid_chain) ile tek LLM çağrısı
9. **evidence** → Chunk + session layer bilgisi toplanır
10. **finalize** → Guard cevapları veya RAG cevabı + evidence dönülecek hale getirilir

Stream için: Aynı node’lar `run_graph_until_route()` ile çalıştırılır, LLM kısmı `astream` ile token token stream edilir, sonra evidence/finalize ile NDJSON `done` gönderilir.

---

## 3. Veritabanları nasıl initialize ediliyor?

### 3.1 Redis (session)

- **Ne işe yarar:** Kullanıcıya özel session JSON (çizim objeleri). Ephemeral; vector DB’ye yazılmaz.
- **Nasıl başlar:** `docker compose` ile `redis:7-alpine` container ayağa kalkar. Ek kurulum yok; Redis boş başlar.
- **İlk kullanım:** Kullanıcı “Update Session” dediğinde Backend `PUT /session/objects` ile Redis’e yazar (`session:{user_id}:objects`). Önceden tablo/collection oluşturmana gerek yok.

### 3.2 SQLite (backend – kullanıcılar)

- **Ne işe yarar:** Kayıt olan kullanıcılar (username, email, hash’lenmiş şifre).
- **Nasıl initialize edilir:** Backend **lifespan**’ta `get_database()` çağırır → `DatabaseService.__init__` çalışır:
  - `data/` (veya `DATABASE_URL`’deki path) yoksa oluşturulur.
  - `Base.metadata.create_all(bind=self.engine)` ile `users` tablosu **otomatik** oluşturulur.
- **Sıfırdan çalıştırma:** `data/` klasörü yoksa backend ilk açılışta oluşturur ve tabloları yazar. Elle DB kurmana gerek yok.

### 3.3 ChromaDB (agent – PDF chunk’ları)

- **Ne işe yarar:** PDF’lerden üretilen metin chunk’ları + embedding’ler. RAG’da similarity search burada.
- **Nasıl initialize edilir:**
  1. **Agent startup (lifespan):**
     - `VectorStoreService()`: `chroma_persist_directory` (örn. `/data/chroma`) oluşturulur, `chromadb.PersistentClient(path=...)` ile client açılır, `get_or_create_collection(...)` ile collection **yoksa oluşturulur**, varsa açılır.
     - `DocumentRegistry(registry_path)`: `document_registry.json` dosyası yoksa oluşturulur / boş başlar.
     - `sync_service.sync()`: `PDF_DATA_DIRECTORY` (örn. `data/pdfs`) taranır, her PDF için hash’e bakılır (NEW/UNCHANGED/UPDATED). Yeni veya değişen PDF’ler chunk’lanıp Chroma’ya eklenir, registry güncellenir.
  2. **Retrieval tarafı:** `retrieval_lc.get_vectorstore()` ilk çağrıda LangChain Chroma’yı **aynı** `persist_directory` ve `collection_name` ile açar (lazy). Aynı Chroma DB’yi kullanır; ek bir “init” adımı yok.

- **Sıfırdan çalıştırma:** `data/pdfs/` boşsa sync “0 new, 0 updated” der, Chroma boş kalır. İçine PDF koyarsan bir sonraki agent restart’ta (veya `/ingest` ile) PDF’ler işlenir ve Chroma dolar. Önceden Chroma’yı elle kurmana gerek yok.

---

## 4. Sıfırdan bu projeyi kopyalayıp çalıştırma (adım adım)

### Gereksinimler

- Docker + Docker Compose
- (Opsiyonel) Git

### Adımlar

1. **Projeyi al**
   ```bash
   git clone https://github.com/NurbukeTeker/aici-conversational-rag.git
   cd aici-conversational-rag
   ```
   veya ZIP indirip aç.

2. **Ortam dosyasını oluştur**
   ```bash
   cp env.example .env
   ```

3. **`.env` içinde zorunlu değişken**
   - `OPENAI_API_KEY=sk-...` → Kendi OpenAI API anahtarını yaz (Agent RAG cevapları için gerekli).
   - (İsteğe bağlı) `JWT_SECRET_KEY` production için değiştir.

4. **(İsteğe bağlı) PDF ekle**
   - `data/pdfs/` klasörüne PDF dosyalarını koy. Agent ilk açılışta bu klasörü tarayıp Chroma’yı dolduracak. Boş bırakırsan RAG boş çalışır (cevaplar sadece session/LLM’den gelir).

5. **Tüm servisleri ayağa kaldır**
   ```bash
   docker compose up --build
   ```
   - İlk seferde image’lar build edilir, sonra:
     - Redis açılır.
     - Agent: Chroma + registry init, sync (PDF varsa chunk’lar yazılır), LangGraph/LCEL hazırlanır.
     - Backend: SQLite tabloları oluşturulur, Redis’e bağlanır.
     - Frontend: Nginx ile servis edilir.

6. **Tarayıcıdan aç**
   - Frontend: http://localhost:3000
   - Register → Login → JSON’u düzenle → “Update Session” → Soru sor. Cevap ve evidence panelden gelir.

### Özet: DB’leri sen mi kuracaksın?

- **Hayır.** Redis sadece container; SQLite tabloları backend ilk açılışta oluşturur; Chroma dizini ve collection agent ilk açılışta (ve sync/ingest ile) oluşturulur. Sıfırdan kopyalayıp `cp env.example .env`, `OPENAI_API_KEY` ekleyip `docker compose up --build` yeterli.

---

## 5. Kısa referans: Hangi servis nerede yazıyor?

| Ne              | Nerede / Nasıl |
|-----------------|----------------|
| Kullanıcı DB    | Backend lifespan → `get_database()` → SQLite `data/users.db`, tablolar `create_all` |
| Session (JSON)  | Backend `PUT /session/objects` → Redis `session:{user_id}:objects` |
| PDF chunk’ları  | Agent startup `sync_service.sync()` veya `POST /ingest` → Chroma (`vector_store.add_documents`) + `document_registry.json` |
| Chroma okuma    | Agent her `/answer` veya `/answer/stream`’de `retrieval_lc.retrieve()` (LangChain Chroma) |

---

## 6. Sorun giderme

- **"An instance of Chroma already exists for ... with different settings":** Eski bir Chroma dizini farklı ayarlarla açılmış olabilir. Tek seferlik çözüm: Chroma volume’unu silip yeniden başlat: `docker compose down` → `docker volume rm aici-conversational-rag_chroma_data` (veya proje adına göre volume adı) → `docker compose up --build`. Agent PDF’leri tekrar sync eder. Kod tarafında artık tek paylaşılan Chroma client kullanıldığı için yeni kurulumlarda bu hata oluşmamalı.
- **Agent 503:** `OPENAI_API_KEY` .env’de doğru mu? Chroma/sync hata verirse log’a bak (örn. `data/pdfs` veya volume izinleri).
- **Backend 503:** Redis ve Agent healthy mi? `docker compose ps` ve backend log’larına bak.
- **Cevap boş / “no relevant chunks”:** `data/pdfs/` içinde PDF var mı? Varsa agent log’unda “Sync result: X new, Y updated” benzeri satır görünmeli. Chroma boşsa RAG tarafı boş döner.
- **502 Bad Gateway:** Backend, Agent’tan hata veya zaman aşımı aldığında 502 döner. Kontrol: (1) Agent ayakta mı? `docker compose ps` ile agent ve backend “healthy” olmalı. (2) `.env` içinde `OPENAI_API_KEY` geçerli mi? (3) Backend log’unda “Agent service error” veya “Error calling agent” var mı? Agent log’unda hata var mı? Agent’ı yeniden başlatıp tekrar dene.
- **WebSocket connection failed / ws://.../api/ws/qa failed:** (1) 502 ise yukarıdaki gibi Agent/backend sağlığını kontrol et. (2) Proxy (nginx veya Vite) WebSocket’i destekliyor mu? Docker ile çalışıyorsan frontend nginx’te `proxy_read_timeout` ve `Connection upgrade` ayarları güncellenmiş olmalı. (3) Geliştirme ortamında Vite kullanıyorsan backend’in `http://localhost:8000` adresinde çalıştığından emin ol; `vite.config.js` içinde `proxy` ve `ws: true` ayarlı.

Bu doküman, projenin nasıl çalıştığını, DB’lerin nasıl initialize edildiğini ve sıfırdan çalıştırma adımlarını tek yerde toplar.
