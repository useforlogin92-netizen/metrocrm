from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_sm_whatsapp_share_targets_entered_mobile_directly():
    template = (ROOT / "app" / "templates" / "property_submission_share.html").read_text(encoding="utf-8")
    assert 'id="whatsappShare"' in template
    assert 'data-recipient-mobile="{{ submission.recipient_mobile or \'\' }}"' in template
    assert "digits.slice(-10)" in template
    assert "'91' + local" in template
    assert "https://wa.me/' + target + '?text='" in template
    assert "does not require the SM number to be saved" in template
