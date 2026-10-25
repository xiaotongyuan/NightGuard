from nightguard.clock import clock_arc_min, circular_median_minutes, forward_elapsed_min, minutes_from_midnight


def test_forward_elapsed_wraps_midnight():
    assert forward_elapsed_min("23:50:00", "00:02:00") == 12
    assert forward_elapsed_min("02:00:00", "02:02:00") == 2


def test_clock_arc_is_shortest():
    assert clock_arc_min("01:55", "02:15") == 20
    assert clock_arc_min("02:15", "01:55") == 20
    assert clock_arc_min("23:30", "00:30") == 60
    assert clock_arc_min("22:00", "00:30") == 150


def test_median_midnight_cluster():
    values = [minutes_from_midnight(t) for t in ("23:40", "23:55", "00:10")]
    assert circular_median_minutes(values) == minutes_from_midnight("23:55")
