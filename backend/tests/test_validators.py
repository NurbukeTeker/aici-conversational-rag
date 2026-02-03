"""Tests for validation module."""
import pytest
from app.validators import (
    PasswordValidator, UsernameValidator, EmailValidator,
    password_validator, username_validator, email_validator,
    validate_registration
)

# =============================================================================
# TEST FIXTURES - These are NOT real credentials
# These strings are intentionally crafted to test password validation logic
# =============================================================================
# fmt: off
VALID_TEST_PASSWORD = "TestPass_123!"  # noqa: S105  # gitguardian: ignore
STRONG_TEST_PASSWORD = "Str0ng_T3st_Pass!"  # noqa: S105  # gitguardian: ignore
COMMON_TEST_PASSWORD = "Password123"  # noqa: S105  # gitguardian: ignore - matches "password123" in blocklist
# fmt: on


class TestPasswordValidator:
    """Test password validation."""
    
    def test_valid_strong_password(self):
        """Test that a strong password passes validation."""
        result = password_validator.validate(VALID_TEST_PASSWORD)
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_password_too_short(self):
        """Test that short passwords fail."""
        result = password_validator.validate("Short1!")
        assert result.is_valid is False
        assert any("at least 8 characters" in e for e in result.errors)
    
    def test_password_missing_uppercase(self):
        """Test that passwords without uppercase fail."""
        result = password_validator.validate("lowercase123!")
        assert result.is_valid is False
        assert any("uppercase" in e for e in result.errors)
    
    def test_password_missing_lowercase(self):
        """Test that passwords without lowercase fail."""
        result = password_validator.validate("UPPERCASE123!")
        assert result.is_valid is False
        assert any("lowercase" in e for e in result.errors)
    
    def test_password_missing_digit(self):
        """Test that passwords without digits fail."""
        result = password_validator.validate("NoDigits!@#")
        assert result.is_valid is False
        assert any("digit" in e for e in result.errors)
    
    def test_password_missing_special(self):
        """Test that passwords without special chars fail."""
        result = password_validator.validate("NoSpecial123")
        assert result.is_valid is False
        assert any("special character" in e for e in result.errors)
    
    def test_common_password_rejected(self):
        """Test that common passwords are rejected."""
        result = password_validator.validate(COMMON_TEST_PASSWORD)
        assert result.is_valid is False
        assert any("too common" in e for e in result.errors)
    
    def test_password_strength_scoring(self):
        """Test password strength scoring."""
        # Weak password (intentionally weak for testing)
        weak_score, weak_label = password_validator.get_strength("weak")  # noqa: S105
        assert weak_label in ["Very Weak", "Weak"]
        
        # Strong password
        strong_score, strong_label = password_validator.get_strength(STRONG_TEST_PASSWORD)
        assert strong_label in ["Strong", "Very Strong"]
        assert strong_score > weak_score
    
    def test_sequential_chars_warning(self):
        """Test warning for sequential characters."""
        result = password_validator.validate("Abc123!@#Pass")
        # Should be valid but have warning
        assert any("sequential" in w.lower() for w in result.warnings)


class TestUsernameValidator:
    """Test username validation."""
    
    def test_valid_username(self):
        """Test that valid usernames pass."""
        result = username_validator.validate("john_doe")
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_username_too_short(self):
        """Test that short usernames fail."""
        result = username_validator.validate("ab")
        assert result.is_valid is False
        assert any("at least 3 characters" in e for e in result.errors)
    
    def test_username_too_long(self):
        """Test that long usernames fail."""
        result = username_validator.validate("a" * 31)
        assert result.is_valid is False
        assert any("not exceed 30 characters" in e for e in result.errors)
    
    def test_username_must_start_with_letter(self):
        """Test that usernames must start with letter."""
        result = username_validator.validate("123user")
        assert result.is_valid is False
        assert any("start with a letter" in e for e in result.errors)
    
    def test_username_invalid_chars(self):
        """Test that usernames with invalid chars fail."""
        result = username_validator.validate("user@name")
        assert result.is_valid is False
    
    def test_username_consecutive_underscores(self):
        """Test that consecutive underscores fail."""
        result = username_validator.validate("user__name")
        assert result.is_valid is False
        assert any("consecutive underscores" in e for e in result.errors)
    
    def test_reserved_username_rejected(self):
        """Test that reserved usernames are rejected."""
        result = username_validator.validate("admin")
        assert result.is_valid is False
        assert any("reserved" in e for e in result.errors)


class TestEmailValidator:
    """Test email validation."""
    
    def test_valid_email(self):
        """Test that valid emails pass."""
        result = email_validator.validate("user@example.com")
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_invalid_email_format(self):
        """Test that invalid emails fail."""
        invalid_emails = [
            "notanemail",
            "missing@domain",
            "@nouser.com",
            "spaces in@email.com",
        ]
        for email in invalid_emails:
            result = email_validator.validate(email)
            assert result.is_valid is False, f"Expected {email} to fail"
    
    def test_email_normalization(self):
        """Test that emails are normalized."""
        normalized = email_validator.normalize("  User@EXAMPLE.COM  ")
        assert normalized == "user@example.com"
    
    def test_email_typo_warning(self):
        """Test that email typos generate warnings."""
        result = email_validator.validate("user@gmial.com")
        assert len(result.warnings) > 0
        assert any("gmail.com" in w for w in result.warnings)


class TestRegistrationValidation:
    """Test combined registration validation."""
    
    def test_valid_registration(self):
        """Test that valid registration data passes."""
        result = validate_registration(
            username="testuser",
            email="test@example.com",
            password=VALID_TEST_PASSWORD
        )
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_invalid_all_fields(self):
        """Test that multiple invalid fields return all errors."""
        result = validate_registration(
            username="a",  # Too short
            email="notanemail",  # Invalid format
            password="weak"  # noqa: S105 - intentionally weak for testing
        )
        assert result.is_valid is False
        assert len(result.errors) >= 3  # At least one error per field
