import pytest

from runa.runtime.driving import DrivingGuard, RunAlreadyDriving


def test_begin_raises_if_the_run_id_is_already_being_driven():
    guard = DrivingGuard()
    guard.begin("run-1")

    with pytest.raises(RunAlreadyDriving):
        guard.begin("run-1")


def test_end_lets_the_run_id_be_driven_again():
    guard = DrivingGuard()
    guard.begin("run-1")
    guard.end("run-1")

    guard.begin("run-1")  # does not raise: the claim was released


def test_different_run_ids_do_not_contend():
    guard = DrivingGuard()
    guard.begin("run-1")

    guard.begin("run-2")  # does not raise: a different run id


def test_end_on_a_run_id_never_begun_is_a_no_op():
    guard = DrivingGuard()

    guard.end("run-1")  # does not raise
