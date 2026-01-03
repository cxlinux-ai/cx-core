from cortex.approval import ApprovalMode
from cortex.approval_policy import get_approval_policy


def test_suggest_policy():
    policy = get_approval_policy(ApprovalMode.SUGGEST)

    assert policy.allow("show")
    assert not policy.allow("shell_command")
    assert not policy.requires_confirmation("shell_command")


def test_auto_edit_policy():
    policy = get_approval_policy(ApprovalMode.AUTO_EDIT)

    assert policy.allow("shell_command")
    assert policy.requires_confirmation("shell_command")


def test_full_auto_policy():
    policy = get_approval_policy(ApprovalMode.FULL_AUTO)

    assert policy.allow("shell_command")
    assert not policy.requires_confirmation("shell_command")
