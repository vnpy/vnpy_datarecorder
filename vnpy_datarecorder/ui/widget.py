"""行情记录管理界面。"""
from datetime import datetime
from typing import cast

from vnpy.event import Event, EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import QtCore, QtWidgets
from vnpy.trader.event import EVENT_CONTRACT
from vnpy.trader.object import ContractData

from ..engine import (
    APP_NAME,
    EVENT_RECORDER_LOG,
    EVENT_RECORDER_UPDATE,
    RecorderEngine
)


class RecorderManager(QtWidgets.QWidget):
    """行情记录管理界面。"""

    signal_log: QtCore.Signal = QtCore.Signal(Event)
    signal_update: QtCore.Signal = QtCore.Signal(Event)
    signal_contract: QtCore.Signal = QtCore.Signal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """取得录制引擎，初始化界面并推送当前记录列表。"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.recorder_engine: RecorderEngine = cast(RecorderEngine, main_engine.get_engine(APP_NAME))

        self.init_ui()
        self.register_event()
        self.recorder_engine.put_event()

    def init_ui(self) -> None:
        """搭建本地代码、写入间隔，以及 K 线、Tick 记录列表和日志。"""
        self.setWindowTitle("行情记录")
        self.resize(1000, 600)

        # Create widgets
        self.symbol_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()

        self.interval_spin: QtWidgets.QSpinBox = QtWidgets.QSpinBox()
        self.interval_spin.setMinimum(1)
        self.interval_spin.setMaximum(60)
        self.interval_spin.setValue(self.recorder_engine.timer_interval)
        self.interval_spin.setSuffix("秒")
        self.interval_spin.valueChanged.connect(self.set_interval)

        contracts: list[ContractData] = self.main_engine.get_all_contracts()
        self.vt_symbols: list = [contract.vt_symbol for contract in contracts]

        self.symbol_completer: QtWidgets.QCompleter = QtWidgets.QCompleter(self.vt_symbols)
        self.symbol_completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        self.symbol_completer.setCompletionMode(self.symbol_completer.CompletionMode.PopupCompletion)
        self.symbol_line.setCompleter(self.symbol_completer)

        add_bar_button: QtWidgets.QPushButton = QtWidgets.QPushButton("添加")
        add_bar_button.clicked.connect(self.add_bar_recording)

        remove_bar_button: QtWidgets.QPushButton = QtWidgets.QPushButton("移除")
        remove_bar_button.clicked.connect(self.remove_bar_recording)

        add_tick_button: QtWidgets.QPushButton = QtWidgets.QPushButton("添加")
        add_tick_button.clicked.connect(self.add_tick_recording)

        remove_tick_button: QtWidgets.QPushButton = QtWidgets.QPushButton("移除")
        remove_tick_button.clicked.connect(self.remove_tick_recording)

        self.bar_recording_edit: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.bar_recording_edit.setReadOnly(True)

        self.tick_recording_edit: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.tick_recording_edit.setReadOnly(True)

        self.log_edit: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.log_edit.setReadOnly(True)

        # Set layout
        grid: QtWidgets.QGridLayout = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("K线记录"), 0, 0)
        grid.addWidget(add_bar_button, 0, 1)
        grid.addWidget(remove_bar_button, 0, 2)
        grid.addWidget(QtWidgets.QLabel("Tick记录"), 1, 0)
        grid.addWidget(add_tick_button, 1, 1)
        grid.addWidget(remove_tick_button, 1, 2)

        form: QtWidgets.QFormLayout = QtWidgets.QFormLayout()
        form.addRow("本地代码", self.symbol_line)
        form.addRow("写入间隔", self.interval_spin)

        hbox: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        hbox.addLayout(form)
        hbox.addWidget(QtWidgets.QLabel("     "))
        hbox.addLayout(grid)
        hbox.addStretch()

        grid2: QtWidgets.QGridLayout = QtWidgets.QGridLayout()
        grid2.addWidget(QtWidgets.QLabel("K线记录列表"), 0, 0)
        grid2.addWidget(QtWidgets.QLabel("Tick记录列表"), 0, 1)
        grid2.addWidget(self.bar_recording_edit, 1, 0)
        grid2.addWidget(self.tick_recording_edit, 1, 1)
        grid2.addWidget(self.log_edit, 2, 0, 1, 2)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addLayout(grid2)
        self.setLayout(vbox)

    def register_event(self) -> None:
        """监听合约、日志和记录列表更新。"""
        self.signal_log.connect(self.process_log_event)
        self.signal_contract.connect(self.process_contract_event)
        self.signal_update.connect(self.process_update_event)

        self.event_engine.register(EVENT_CONTRACT, self.signal_contract.emit)
        self.event_engine.register(EVENT_RECORDER_LOG, self.signal_log.emit)
        self.event_engine.register(EVENT_RECORDER_UPDATE, self.signal_update.emit)

    def process_log_event(self, event: Event) -> None:
        """把当前时间和日志内容追加到日志框。"""
        timestamp: str = datetime.now().strftime("%H:%M:%S")
        msg: str = f"{timestamp}\t{event.data}"
        self.log_edit.append(msg)

    def process_update_event(self, event: Event) -> None:
        """用事件里的代码列表刷新 K 线和 Tick 记录显示。"""
        data: dict = event.data

        self.bar_recording_edit.clear()
        bar_text: str = "\n".join(data["bar"])
        self.bar_recording_edit.setText(bar_text)

        self.tick_recording_edit.clear()
        tick_text: str = "\n".join(data["tick"])
        self.tick_recording_edit.setText(tick_text)

    def process_contract_event(self, event: Event) -> None:
        """把新合约的本地代码加入自动补全。"""
        contract: ContractData = event.data
        self.vt_symbols.append(contract.vt_symbol)

        model: QtCore.QStringListModel = cast(QtCore.QStringListModel, self.symbol_completer.model())
        model.setStringList(self.vt_symbols)

    def add_bar_recording(self) -> None:
        """按输入的本地代码添加 K 线记录。"""
        vt_symbol: str = self.symbol_line.text()
        self.recorder_engine.add_bar_recording(vt_symbol)

    def add_tick_recording(self) -> None:
        """按输入的本地代码添加 Tick 记录。"""
        vt_symbol: str = self.symbol_line.text()
        self.recorder_engine.add_tick_recording(vt_symbol)

    def remove_bar_recording(self) -> None:
        """按输入的本地代码移除 K 线记录。"""
        vt_symbol: str = self.symbol_line.text()
        self.recorder_engine.remove_bar_recording(vt_symbol)

    def remove_tick_recording(self) -> None:
        """按输入的本地代码移除 Tick 记录。"""
        vt_symbol: str = self.symbol_line.text()
        self.recorder_engine.remove_tick_recording(vt_symbol)

    def set_interval(self, interval: int) -> None:
        """把录制引擎的定时写库间隔设为给定秒数。"""
        self.recorder_engine.timer_interval = interval
