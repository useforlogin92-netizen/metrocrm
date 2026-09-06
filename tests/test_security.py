from app.security import generate_otp, hash_password, otp_is_valid, verify_password


def test_password_round_trip():
    encoded = hash_password("synthetic-test-password")
    assert verify_password("synthetic-test-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_otp_is_six_digits_and_expires():
    otp = generate_otp()
    assert len(otp) == 6 and otp.isdigit()
    assert otp_is_valid(1000.0, 1004.0, 5)
    assert not otp_is_valid(1000.0, 1006.0, 5)
