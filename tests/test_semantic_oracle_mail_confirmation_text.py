"""Exact typed mail confirmation wording."""

import pytest

from alas_headless.oracle.errors import SemanticGateClosed
from alas_headless.oracle.mail import classify_mail_confirmation_text


def test_current_cn_read_mail_delete_confirmation():
    text = (
        "确定要删除选中的已读邮件吗？"
        "<color=#238c40>（未领取附件的邮件将会保留）</color>"
    )
    assert classify_mail_confirmation_text(text) == "delete"


def test_unreviewed_mail_delete_wording_stays_closed():
    with pytest.raises(SemanticGateClosed, match="unsupported"):
        classify_mail_confirmation_text("确定要删除所有邮件吗？")
