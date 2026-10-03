"""行情记录引擎。"""
import traceback
from threading import Thread
from queue import Queue, Empty
from copy import copy
from collections import defaultdict
from datetime import datetime, timedelta

from vnpy.event import Event, EventEngine
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.trader.constant import Exchange
from vnpy.trader.object import (
    SubscribeRequest,
    TickData,
    BarData,
    ContractData
)
from vnpy.trader.event import EVENT_TICK, EVENT_CONTRACT, EVENT_TIMER
from vnpy.trader.utility import load_json, save_json, BarGenerator
from vnpy.trader.database import BaseDatabase, get_database, DB_TZ
from vnpy_spreadtrading.base import EVENT_SPREAD_DATA, SpreadItem


APP_NAME = "DataRecorder"

EVENT_RECORDER_LOG = "eRecorderLog"
EVENT_RECORDER_UPDATE = "eRecorderUpdate"


class RecorderEngine(BaseEngine):
    """
    用于运行行情记录。
    """

    setting_filename: str = "data_recorder_setting.json"

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """初始化录制队列和过滤窗口，加载配置后开始录制。"""
        super().__init__(main_engine, event_engine, APP_NAME)

        self.queue: Queue = Queue()
        self.thread: Thread = Thread(target=self.run)
        self.active: bool = False

        self.tick_recordings: dict[str, dict] = {}
        self.bar_recordings: dict[str, dict] = {}
        self.bar_generators: dict[str, BarGenerator] = {}

        self.timer_count: int = 0
        self.timer_interval: int = 10

        self.ticks: dict[str, list[TickData]] = defaultdict(list)
        self.bars: dict[str, list[BarData]] = defaultdict(list)

        self.filter_dt: datetime = datetime.now(DB_TZ)      # Tick数据过滤的时间戳
        self.filter_window: int = 60                        # Tick数据过滤的时间窗口，默认60秒
        self.filter_delta: timedelta                        # Tick数据过滤的时间偏差对象

        self.database: BaseDatabase = get_database()

        self.load_setting()
        self.register_event()
        self.start()
        self.put_event()

    def load_setting(self) -> None:
        """读取 Tick、K 线记录列表和 Tick 过滤窗口。"""
        setting: dict = load_json(self.setting_filename)
        self.tick_recordings = setting.get("tick", {})
        self.bar_recordings = setting.get("bar", {})

        self.filter_window = setting.get("filter_window", 60)
        self.filter_delta = timedelta(seconds=self.filter_window)

    def save_setting(self) -> None:
        """把 Tick 和 K 线记录列表写入配置文件。"""
        setting: dict = {
            "tick": self.tick_recordings,
            "bar": self.bar_recordings
        }
        save_json(self.setting_filename, setting)

    def run(self) -> None:
        """循环取出队列中的 Tick 或 K 线写入数据库，异常时停止录制并写日志。"""
        while self.active:
            try:
                task: tuple[str, list] = self.queue.get(timeout=1)
                task_type, data = task

                if task_type == "tick":
                    self.database.save_tick_data(data, stream=True)
                elif task_type == "bar":
                    self.database.save_bar_data(data, stream=True)

            except Empty:
                continue

            except Exception:
                self.active = False

                info: str = traceback.format_exc()
                self.write_log(f"触发异常，录制已停止：\n{info}")

    def close(self) -> None:
        """停止录制并等待线程结束。"""
        self.active = False

        if self.thread.is_alive():
            self.thread.join()

    def start(self) -> None:
        """标记为运行中并启动录制线程。"""
        self.active = True
        self.thread.start()

    def add_bar_recording(self, vt_symbol: str) -> None:
        """已在列表中则写日志并返回；本地交易所代码直接加入，其他代码找不到合约则返回，否则订阅后加入 K 线记录并保存。"""
        if vt_symbol in self.bar_recordings:
            self.write_log(f"已在K线记录列表中：{vt_symbol}")
            return

        if Exchange.LOCAL.value not in vt_symbol:
            contract: ContractData | None = self.main_engine.get_contract(vt_symbol)
            if not contract:
                self.write_log(f"找不到合约：{vt_symbol}")
                return

            self.bar_recordings[vt_symbol] = {
                "symbol": contract.symbol,
                "exchange": contract.exchange.value,
                "gateway_name": contract.gateway_name
            }

            self.subscribe(contract)
        else:
            self.bar_recordings[vt_symbol] = {}

        self.save_setting()
        self.put_event()

        self.write_log(f"添加K线记录成功：{vt_symbol}")

    def add_tick_recording(self, vt_symbol: str) -> None:
        """已在列表中则写日志并返回；本地交易所代码直接加入，其他代码找不到合约则返回，否则订阅后加入 Tick 记录并保存。"""
        if vt_symbol in self.tick_recordings:
            self.write_log(f"已在Tick记录列表中：{vt_symbol}")
            return

        # For normal contract
        if Exchange.LOCAL.value not in vt_symbol:
            contract: ContractData | None = self.main_engine.get_contract(vt_symbol)
            if not contract:
                self.write_log(f"找不到合约：{vt_symbol}")
                return

            self.tick_recordings[vt_symbol] = {
                "symbol": contract.symbol,
                "exchange": contract.exchange.value,
                "gateway_name": contract.gateway_name
            }

            self.subscribe(contract)
        # No need to subscribe for spread data
        else:
            self.tick_recordings[vt_symbol] = {}

        self.save_setting()
        self.put_event()

        self.write_log(f"添加Tick记录成功：{vt_symbol}")

    def remove_bar_recording(self, vt_symbol: str) -> None:
        """不在 K 线记录列表时写日志并返回，否则移除并保存。"""
        if vt_symbol not in self.bar_recordings:
            self.write_log(f"不在K线记录列表中：{vt_symbol}")
            return

        self.bar_recordings.pop(vt_symbol)
        self.save_setting()
        self.put_event()

        self.write_log(f"移除K线记录成功：{vt_symbol}")

    def remove_tick_recording(self, vt_symbol: str) -> None:
        """不在 Tick 记录列表时写日志并返回，否则移除并保存。"""
        if vt_symbol not in self.tick_recordings:
            self.write_log(f"不在Tick记录列表中：{vt_symbol}")
            return

        self.tick_recordings.pop(vt_symbol)
        self.save_setting()
        self.put_event()

        self.write_log(f"移除Tick记录成功：{vt_symbol}")

    def register_event(self) -> None:
        """监听定时器、行情、合约和价差事件。"""
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)
        self.event_engine.register(EVENT_TICK, self.process_tick_event)
        self.event_engine.register(EVENT_CONTRACT, self.process_contract_event)
        self.event_engine.register(EVENT_SPREAD_DATA, self.process_spread_event)

    def update_tick(self, tick: TickData) -> None:
        """与本地时间相差达到过滤窗口的 Tick 直接丢弃，其余写入 Tick 记录或更新 K 线。"""
        # 过滤偏离本地时间戳过大的Tick数据
        tick_delta: timedelta = abs(tick.datetime - self.filter_dt)
        if abs(tick_delta) >= self.filter_delta:
            return

        if tick.vt_symbol in self.tick_recordings:
            self.record_tick(copy(tick))

        if tick.vt_symbol in self.bar_recordings:
            bg: BarGenerator = self.get_bar_generator(tick.vt_symbol)
            bg.update_tick(copy(tick))

    def process_timer_event(self, event: Event) -> None:
        """刷新本地时间，每隔 timer_interval 次把缓存的 K 线和 Tick 放入写库队列并清空缓存。"""
        self.filter_dt = datetime.now(DB_TZ)

        self.timer_count += 1
        if self.timer_count < self.timer_interval:
            return
        self.timer_count = 0

        for bars in self.bars.values():
            self.queue.put(("bar", bars))
        self.bars.clear()

        for ticks in self.ticks.values():
            self.queue.put(("tick", ticks))
        self.ticks.clear()

    def process_tick_event(self, event: Event) -> None:
        """取出行情并按记录规则更新。"""
        tick: TickData = event.data
        self.update_tick(tick)

    def process_contract_event(self, event: Event) -> None:
        """合约已在 Tick 或 K 线记录列表中时订阅行情。"""
        contract: ContractData = event.data
        vt_symbol: str = contract.vt_symbol

        if (vt_symbol in self.tick_recordings or vt_symbol in self.bar_recordings):
            self.subscribe(contract)

    def process_spread_event(self, event: Event) -> None:
        """把价差转成 Tick；时间为空则跳过，否则按记录规则更新。"""
        spread_item: SpreadItem = event.data
        tick: TickData = TickData(
            symbol=spread_item.name,
            exchange=Exchange.LOCAL,
            datetime=spread_item.datetime,
            name=spread_item.name,
            last_price=(spread_item.bid_price + spread_item.ask_price) / 2,
            bid_price_1=spread_item.bid_price,
            ask_price_1=spread_item.ask_price,
            bid_volume_1=spread_item.bid_volume,
            ask_volume_1=spread_item.ask_volume,
            localtime=spread_item.datetime,
            gateway_name="SPREAD"
        )

        # Filter not inited spread data
        if tick.datetime:
            self.update_tick(tick)

    def write_log(self, msg: str) -> None:
        """推送行情记录日志事件。"""
        event: Event = Event(
            EVENT_RECORDER_LOG,
            msg
        )
        self.event_engine.put(event)

    def put_event(self) -> None:
        """推送排序后的 Tick 和 K 线记录代码列表。"""
        tick_symbols: list[str] = list(self.tick_recordings.keys())
        tick_symbols.sort()

        bar_symbols: list[str] = list(self.bar_recordings.keys())
        bar_symbols.sort()

        data: dict = {
            "tick": tick_symbols,
            "bar": bar_symbols
        }

        event: Event = Event(
            EVENT_RECORDER_UPDATE,
            data
        )
        self.event_engine.put(event)

    def record_tick(self, tick: TickData) -> None:
        """把 Tick 追加到待写入缓存。"""
        self.ticks[tick.vt_symbol].append(tick)

    def record_bar(self, bar: BarData) -> None:
        """把 K 线追加到待写入缓存。"""
        self.bars[bar.vt_symbol].append(bar)

    def get_bar_generator(self, vt_symbol: str) -> BarGenerator:
        """返回该合约的 K 线生成器，没有则新建。"""
        bg: BarGenerator | None = self.bar_generators.get(vt_symbol, None)

        if not bg:
            bg = BarGenerator(self.record_bar)
            self.bar_generators[vt_symbol] = bg

        return bg

    def subscribe(self, contract: ContractData) -> None:
        """向合约所属接口订阅行情。"""
        req: SubscribeRequest = SubscribeRequest(
            symbol=contract.symbol,
            exchange=contract.exchange
        )
        self.main_engine.subscribe(req, contract.gateway_name)
