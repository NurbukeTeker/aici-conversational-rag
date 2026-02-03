"""Comprehensive validators for user registration."""
import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PasswordValidator:
    """
    Password strength validator with configurable rules.
    
    Default rules:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    - At least 1 special character
    - No common patterns (123456, password, etc.)
    """
    
    # Common weak passwords to block
    COMMON_PASSWORDS = {
        "password", "password123", "123456", "12345678", "qwerty",
        "abc123", "monkey", "1234567", "letmein", "trustno1",
        "dragon", "baseball", "iloveyou", "master", "sunshine",
        "ashley", "bailey", "shadow", "123123", "654321",
        "superman", "qazwsx", "michael", "football", "password1"
    }
    
    def __init__(
        self,
        min_length: int = 8,
        max_length: int = 128,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_digit: bool = True,
        require_special: bool = True,
        special_characters: str = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_digit = require_digit
        self.require_special = require_special
        self.special_characters = special_characters
    
    def validate(self, password: str) -> ValidationResult:
        """Validate password and return detailed result."""
        errors = []
        warnings = []
        
        # Length checks
        if len(password) < self.min_length:
            errors.append(f"Password must be at least {self.min_length} characters long")
        
        if len(password) > self.max_length:
            errors.append(f"Password must not exceed {self.max_length} characters")
        
        # Character type checks
        if self.require_uppercase and not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        
        if self.require_lowercase and not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        
        if self.require_digit and not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")
        
        if self.require_special:
            escaped_special = re.escape(self.special_characters)
            if not re.search(f'[{escaped_special}]', password):
                errors.append("Password must contain at least one special character (!@#$%^&*...)")
        
        # Common password check
        if password.lower() in self.COMMON_PASSWORDS:
            errors.append("Password is too common. Please choose a stronger password")
        
        # Sequential characters check
        if self._has_sequential_chars(password):
            warnings.append("Password contains sequential characters (e.g., 123, abc)")
        
        # Repeated characters check
        if self._has_repeated_chars(password):
            warnings.append("Password contains repeated characters (e.g., aaa, 111)")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _has_sequential_chars(self, password: str, min_seq: int = 3) -> bool:
        """Check for sequential characters."""
        sequences = [
            "0123456789",
            "abcdefghijklmnopqrstuvwxyz",
            "qwertyuiop",
            "asdfghjkl",
            "zxcvbnm"
        ]
        
        password_lower = password.lower()
        for seq in sequences:
            for i in range(len(seq) - min_seq + 1):
                if seq[i:i + min_seq] in password_lower:
                    return True
        return False
    
    def _has_repeated_chars(self, password: str, min_repeat: int = 3) -> bool:
        """Check for repeated characters."""
        for i in range(len(password) - min_repeat + 1):
            if len(set(password[i:i + min_repeat])) == 1:
                return True
        return False
    
    def get_strength(self, password: str) -> tuple[int, str]:
        """
        Calculate password strength score (0-100) and label.
        
        Returns:
            Tuple of (score, label) where label is one of:
            "Very Weak", "Weak", "Fair", "Strong", "Very Strong"
        """
        score = 0
        
        # Length bonus
        length = len(password)
        if length >= 8:
            score += 20
        if length >= 12:
            score += 10
        if length >= 16:
            score += 10
        
        # Character variety bonus
        if re.search(r'[a-z]', password):
            score += 10
        if re.search(r'[A-Z]', password):
            score += 15
        if re.search(r'\d', password):
            score += 15
        if re.search(f'[{re.escape(self.special_characters)}]', password):
            score += 20
        
        # Deductions
        if password.lower() in self.COMMON_PASSWORDS:
            score = max(0, score - 50)
        if self._has_sequential_chars(password):
            score = max(0, score - 10)
        if self._has_repeated_chars(password):
            score = max(0, score - 10)
        
        # Determine label
        if score < 20:
            label = "Very Weak"
        elif score < 40:
            label = "Weak"
        elif score < 60:
            label = "Fair"
        elif score < 80:
            label = "Strong"
        else:
            label = "Very Strong"
        
        return min(100, score), label


class UsernameValidator:
    """
    Username validator with configurable rules.
    
    Default rules:
    - 3-30 characters
    - Alphanumeric and underscore only
    - Must start with a letter
    - No consecutive underscores
    - Not a reserved word
    """
    
    RESERVED_USERNAMES = {
        "admin", "administrator", "root", "system", "api",
        "www", "mail", "email", "support", "help", "info",
        "news", "blog", "shop", "store", "app", "web",
        "null", "undefined", "anonymous", "guest", "user",
        "test", "testing", "demo", "example", "sample"
    }
    
    def __init__(
        self,
        min_length: int = 3,
        max_length: int = 30,
        allowed_pattern: str = r'^[a-zA-Z][a-zA-Z0-9_]*$',
        allow_reserved: bool = False
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.allowed_pattern = allowed_pattern
        self.allow_reserved = allow_reserved
    
    def validate(self, username: str) -> ValidationResult:
        """Validate username and return detailed result."""
        errors = []
        
        # Length checks
        if len(username) < self.min_length:
            errors.append(f"Username must be at least {self.min_length} characters long")
        
        if len(username) > self.max_length:
            errors.append(f"Username must not exceed {self.max_length} characters")
        
        # Pattern check
        if not re.match(self.allowed_pattern, username):
            errors.append(
                "Username must start with a letter and contain only letters, "
                "numbers, and underscores"
            )
        
        # Consecutive underscores
        if "__" in username:
            errors.append("Username cannot contain consecutive underscores")
        
        # Reserved words
        if not self.allow_reserved and username.lower() in self.RESERVED_USERNAMES:
            errors.append("This username is reserved and cannot be used")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors
        )


class EmailValidator:
    """
    Email validator with format and domain checks.
    
    Rules:
    - Valid email format (RFC 5322 compliant, simplified)
    - No plus addressing (optional)
    - Domain not in blocklist (optional)
    """
    
    # Simplified RFC 5322 email pattern
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    # Common disposable email domains
    DISPOSABLE_DOMAINS = {
        "tempmail.com", "throwaway.email", "guerrillamail.com",
        "10minutemail.com", "mailinator.com", "temp-mail.org",
        "fakeinbox.com", "trashmail.com", "getnada.com"
    }
    
    def __init__(
        self,
        allow_plus_addressing: bool = True,
        block_disposable: bool = False,
        custom_blocked_domains: set[str] | None = None
    ):
        self.allow_plus_addressing = allow_plus_addressing
        self.block_disposable = block_disposable
        self.blocked_domains = custom_blocked_domains or set()
        if block_disposable:
            self.blocked_domains.update(self.DISPOSABLE_DOMAINS)
    
    def validate(self, email: str) -> ValidationResult:
        """Validate email and return detailed result."""
        errors = []
        warnings = []
        
        # Normalize
        email = email.strip().lower()
        
        # Basic format check
        if not self.EMAIL_PATTERN.match(email):
            errors.append("Please enter a valid email address")
            return ValidationResult(is_valid=False, errors=errors)
        
        # Plus addressing check
        if not self.allow_plus_addressing and "+" in email.split("@")[0]:
            errors.append("Plus addressing (+) is not allowed in email addresses")
        
        # Extract domain
        domain = email.split("@")[1]
        
        # Disposable domain check
        if domain in self.blocked_domains:
            errors.append("Please use a non-disposable email address")
        
        # Common typo detection
        common_typos = {
            "gmial.com": "gmail.com",
            "gmai.com": "gmail.com",
            "gamil.com": "gmail.com",
            "hotmal.com": "hotmail.com",
            "homail.com": "hotmail.com",
            "outlok.com": "outlook.com",
            "yahooo.com": "yahoo.com",
        }
        if domain in common_typos:
            warnings.append(f"Did you mean {common_typos[domain]}?")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    @staticmethod
    def normalize(email: str) -> str:
        """Normalize email for comparison."""
        return email.strip().lower()


# Default validator instances
password_validator = PasswordValidator()
username_validator = UsernameValidator()
email_validator = EmailValidator()


def validate_registration(
    username: str,
    email: str,
    password: str
) -> ValidationResult:
    """
    Validate all registration fields and return combined result.
    """
    all_errors = []
    all_warnings = []
    
    # Validate username
    username_result = username_validator.validate(username)
    if not username_result.is_valid:
        all_errors.extend([f"Username: {e}" for e in username_result.errors])
    
    # Validate email
    email_result = email_validator.validate(email)
    if not email_result.is_valid:
        all_errors.extend([f"Email: {e}" for e in email_result.errors])
    all_warnings.extend(email_result.warnings)
    
    # Validate password
    password_result = password_validator.validate(password)
    if not password_result.is_valid:
        all_errors.extend([f"Password: {e}" for e in password_result.errors])
    all_warnings.extend(password_result.warnings)
    
    return ValidationResult(
        is_valid=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings
    )
