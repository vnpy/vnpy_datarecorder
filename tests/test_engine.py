import time
from collections.abc import Callable, Iterator
from datetime import datetime

import pytest

from vnpy.event import Event
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.database import DB_TZ
from vnpy.trader.event import EVENT_TICK, EVENT_TIMER
from vnpy.trader.object import BarData, TickData
from vnpy.trader.utility import save_json

from vnpy_datarecorder.engine import RecorderEngine


ANCHOR: datetime = datetime(2024, 1, 2, 9, 0, 30, tzinfo=DB_TZ)
TICK_TIME: datetime = datetime(2024, 1, 2, 9, 0, 40, tzinfo=DB_TZ)
BAR_FIRST: datetime = datetime(2024, 1, 2, 9, 0, 10, tzinfo=DB_TZ)
BAR_SECOND: datetime = datetime(2024, 1, 2, 9, 0, 40, tzinfo=DB_TZ)
BAR_NEXT: datetime = datetime(2024, 1, 2, 9, 1, 5, tzinfo=DB_TZ)


class RecordingDatabase:
    def __init__(self) -> None:
        self.tick_batches: list[tuple[list[TickData], bool]] = []
        self.bar_batches: list[tuple[list[BarData], bool]] = []

    def save_tick_data(self, ticks: list[TickData], stream: bool = False) -> bool:
        self.tick_batches.append((list(ticks), stream))
        return True

    def save_bar_data(self, bars: list[BarData], stream: bool = False) -> bool:
        self.bar_batches.append((list(bars), stream))
        return True


class FakeMainEngine:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[object, str]] = []

    def get_contract(self, vt_symbol: str) -> None:
        return None

    def subscribe(self, req: object, gateway_name: str) -> None:
        self.subscriptions.append((req, gateway_name))


class RecordingEventEngine:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def register(self, event_type: str, handler: Callable[[Event], None]) -> None:
        return None

    def put(self, event: Event) -> None:
        self.events.append(event)


def make_tick(
    symbol: str,
    when: datetime,
    last_price: float,
    volume: float = 0,
    turnover: float = 0,
    open_interest: float = 0,
    high_price: float = 0,
    low_price: float = 0,
) -> TickData:
    return TickData(
        gateway_name="FAKE",
        symbol=symbol,
        exchange=Exchange.SHFE,
        datetime=when,
        last_price=last_price,
        volume=volume,
        turnover=turnover,
        open_interest=open_interest,
        high_price=high_price,
        low_price=low_price,
    )


def prepare(engine: RecorderEngine) -> None:
    # 样本时间固定在锚点附近，避免先被 60 秒窗口丢掉。
    engine.filter_dt = ANCHOR
    engine.timer_interval = 1
    engine.timer_count = 0


def send(engine: RecorderEngine, tick: TickData) -> None:
    engine.process_tick_event(Event(EVENT_TICK, tick))


def flush(engine: RecorderEngine) -> None:
    engine.process_timer_event(Event(EVENT_TIMER))


def wait_for(predicate: Callable[[], bool]) -> bool:
    deadline: float = time.monotonic() + 3
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def open_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[dict[str, object]], tuple[RecorderEngine, RecordingDatabase, FakeMainEngine]]]:
    opened: list[RecorderEngine] = []

    def open_engine(
        setting: dict[str, object],
    ) -> tuple[RecorderEngine, RecordingDatabase, FakeMainEngine]:
        database: RecordingDatabase = RecordingDatabase()
        main_engine: FakeMainEngine = FakeMainEngine()

        def get_database() -> RecordingDatabase:
            return database

        monkeypatch.setattr("vnpy_datarecorder.engine.get_database", get_database)
        save_json(RecorderEngine.setting_filename, setting)
        engine: RecorderEngine = RecorderEngine(main_engine, RecordingEventEngine())  # type: ignore[arg-type]
        opened.append(engine)
        return engine, database, main_engine

    yield open_engine

    for engine in opened:
        engine.close()


def test_tick_recorded_only_for_configured_symbol(
    open_recorder: Callable[
        [dict[str, object]],
        tuple[RecorderEngine, RecordingDatabase, FakeMainEngine],
    ],
) -> None:
    engine, database, main_engine = open_recorder(
        {
            "tick": {
                "rb2501.SHFE": {
                    "symbol": "rb2501",
                    "exchange": "SHFE",
                    "gateway_name": "FAKE",
                },
            },
            "bar": {},
            "filter_window": 60,
        }
    )
    assert set(engine.tick_recordings) == {"rb2501.SHFE"}
    assert engine.bar_recordings == {}
    prepare(engine)
    send(engine, make_tick("rb2501", TICK_TIME, 3500))
    send(engine, make_tick("ag2506", TICK_TIME, 1))
    flush(engine)

    assert wait_for(lambda: len(database.tick_batches) == 1), database.tick_batches
    ticks, stream = database.tick_batches[0]
    assert stream is True
    assert [tick.vt_symbol for tick in ticks] == ["rb2501.SHFE"]
    assert ticks[0].symbol == "rb2501"
    assert ticks[0].exchange == Exchange.SHFE
    assert ticks[0].datetime == TICK_TIME
    assert ticks[0].last_price == 3500
    assert database.bar_batches == []
    assert main_engine.subscriptions == []


def test_bar_recorded_only_for_configured_symbol(
    open_recorder: Callable[
        [dict[str, object]],
        tuple[RecorderEngine, RecordingDatabase, FakeMainEngine],
    ],
) -> None:
    engine, database, main_engine = open_recorder(
        {
            "tick": {},
            "bar": {
                "ag2506.SHFE": {
                    "symbol": "ag2506",
                    "exchange": "SHFE",
                    "gateway_name": "FAKE",
                },
            },
            "filter_window": 60,
        }
    )
    assert set(engine.bar_recordings) == {"ag2506.SHFE"}
    assert engine.tick_recordings == {}
    prepare(engine)
    send(
        engine,
        make_tick("ag2506", BAR_FIRST, 100, volume=10, turnover=1000, open_interest=10, high_price=100, low_price=100),
    )
    send(engine, make_tick("rb2501", BAR_FIRST, 1, volume=1, high_price=1, low_price=1))
    send(
        engine,
        make_tick(
            "ag2506",
            BAR_SECOND,
            104,
            volume=16,
            turnover=1600,
            open_interest=50,
            high_price=105,
            low_price=99,
        ),
    )
    send(engine, make_tick("rb2501", BAR_SECOND, 2, volume=2, high_price=2, low_price=2))
    send(engine, make_tick("ag2506", BAR_NEXT, 103, volume=20, turnover=2000, open_interest=51))
    send(engine, make_tick("rb2501", BAR_NEXT, 3, volume=3, high_price=3, low_price=3))
    flush(engine)

    assert wait_for(lambda: len(database.bar_batches) == 1), database.bar_batches
    bars, stream = database.bar_batches[0]
    assert stream is True
    assert len(bars) == 1
    bar: BarData = bars[0]
    assert bar.vt_symbol == "ag2506.SHFE"
    assert bar.symbol == "ag2506"
    assert bar.exchange == Exchange.SHFE
    assert bar.interval == Interval.MINUTE
    assert bar.gateway_name == "FAKE"
    assert bar.datetime == datetime(2024, 1, 2, 9, 0, tzinfo=DB_TZ)
    assert bar.open_price == 100
    assert bar.high_price == 105
    assert bar.low_price == 99
    assert bar.close_price == 104
    assert bar.volume == 6
    assert bar.turnover == 600
    assert bar.open_interest == 50
    assert database.tick_batches == []
    assert main_engine.subscriptions == []
