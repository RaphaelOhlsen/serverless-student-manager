from tools.bootstrap_admin.normalization import normalize_email, normalize_name


def test_normalize_email_trims_and_lowercases() -> None:
    assert normalize_email("  Admin.Example@Example.COM  ") == "admin.example@example.com"


def test_normalize_name_trims_and_casefolds() -> None:
    assert normalize_name("  Maria Silva  ") == "maria silva"


def test_normalize_name_collapses_internal_whitespace() -> None:
    assert normalize_name("Maria   da\tSilva") == "maria da silva"


def test_normalize_name_applies_unicode_nfkc() -> None:
    assert normalize_name("ＡＤＭＩＮ") == "admin"


def test_normalize_name_uses_unicode_casefold() -> None:
    assert normalize_name("Straße") == "strasse"
