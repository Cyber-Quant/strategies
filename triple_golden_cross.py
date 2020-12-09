import datetime
import json
import numpy as np
import time

from qtpy.QtWidgets import *
from qtpy.QtGui import *
from qtpy.QtCore import *

from conf.conf import strategies_config_path
from strategies.common import get_latest_batch_data, calc_batch_ma, \
    calc_batch_mav, calc_wpct
from strategies.macd import MACD


class TripleGoldenCrossInfo:
    def __init__(self):
        self.name = 'TripleGoldenCross'
        self.desc = '''
        三金叉
        均线，均量线，MACD三者都金叉。代表价，量，时，空这四大要素中有三个发出了买入信号。
        5(m)日快线，10(n)日慢线
        5(k)日内，符合条件
        '''
        self.choose_flag = True
        self.watch_flag = False


class TripleGoldenCross:
    def __init__(self):
        self.config_path = strategies_config_path.joinpath(
            'triple_golden_cross.json')
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.m = data['m']
                self.n = data['n']
                self.k = data['k']
        else:
            self.m = 5
            self.n = 10
            self.k = 5

        # FIXME: I'm not sure should we change the MACD periods here.
        #  if we do, add three args in the MACD __init__.
        self.macd = MACD()

    def calc_fast_ma(self, close):
        ma = calc_batch_ma(close, self.m)
        _ma = [0] * self.m
        ma = _ma + ma
        return ma

    def calc_slow_ma(self, close):
        ma = calc_batch_ma(close, self.n)
        _ma = [0] * self.n
        ma = _ma + ma
        return ma

    def calc_season_ma_indicator(self, close):
        ma = calc_batch_ma(close, 60)
        _ma = [0] * 60
        ma = _ma + ma
        return ma

    def calc_fast_mav(self, volume):
        mav = calc_batch_mav(volume, self.m)
        _mav = [0] * self.m
        mav = _mav + mav
        return mav

    def calc_slow_mav(self, volume):
        mav = calc_batch_mav(volume, self.n)
        _mav = [0] * self.n
        mav = _mav + mav
        return mav

    def backtest(self, code, s_date, e_date, init_money, fee, pass_fee, tax):
        dates, opens, closes, highs, lows, volumes, ma_price, ma_volume = \
            get_latest_batch_data(code, s_date=s_date, e_date=e_date)
        fast_ma = self.calc_fast_ma(closes)
        slow_ma = self.calc_slow_ma(closes)
        fast_mav = self.calc_fast_mav(volumes)
        slow_mav = self.calc_slow_mav(volumes)
        macd, dif, dea = self.macd.calc_macd(closes)
        if self.m > self.n:
            start = self.m
        else:
            start = self.n
        buy_prices = []
        buy_dates = []
        buy_index = []
        sell_prices = []
        sell_dates = []
        sell_index = []
        drawdowns = []
        old_state = 's'
        for i, x in enumerate(closes):
            if i < start:
                continue
            if i == start:
                continue
            if (fast_ma[i - self.k] < slow_ma[i - self.k] \
                and fast_ma[i - 1] > slow_ma[i - 1]) \
                    and (fast_mav[i - self.k] < slow_mav[i - self.k] \
                         and fast_mav[i - 1] > slow_mav[i - 1]) \
                    and (macd[i - self.k] < 0 and macd[i - 1] > 0):
                state = 'b'
                if state != old_state:
                    buy_prices.append(closes[i])
                    buy_dates.append(dates[i])
                    buy_index.append(i)
                    old_state = state
            elif (fast_ma[i - self.k] > slow_ma[i - self.k] \
                  and fast_ma[i - 1] < slow_ma[i - 1]) \
                    or (fast_mav[i - self.k] > slow_mav[i - self.k] \
                        and fast_mav[i - 1] < slow_mav[i - 1]) \
                    or (macd[i - self.k] > 0 and macd[i - 1] < 0):
                state = 's'
                if state != old_state:
                    sell_prices.append(closes[i])
                    sell_dates.append(dates[i])
                    sell_index.append(i)
                    old_state = state
        if len(sell_prices) < len(buy_prices):
            sell_prices.append(closes[-1])
            sell_dates.append(dates[-1])
            sell_index.append(len(buy_prices))

        money = init_money
        opening_index_slices = []
        opening_price_slices = []
        closing_index_slices = []
        closing_price_slices = []
        for i in range(len(buy_prices)):
            hands = int(money * (1 - fee) / buy_prices[i] / 100)
            left_money = money - hands * buy_prices[i] * 100
            sell_money = hands * sell_prices[i] * (1 - tax - pass_fee) * 100
            money = sell_money + left_money

            old_close = buy_prices[i]
            for close in closes[buy_index[i]:sell_index[i] + 1]:
                if close < old_close:
                    old_close = close
            drawdown = buy_prices[i] - old_close / buy_prices[i] * 100
            drawdowns.append(drawdown)
            if i == 0:
                first_start = 0
            else:
                first_start = sell_index[i - 1]
            closing_index = []
            closing_price = []
            for idx in range(first_start, buy_index[i] + 1):
                closing_index.append(idx)
                closing_price.append(closes[idx])
            closing_index_slices.append(closing_index)
            closing_price_slices.append(closing_price)
            opening_index = []
            opening_price = []
            for idx in range(buy_index[i], sell_index[i] + 1):
                opening_index.append(idx)
                opening_price.append(closes[idx])
            if opening_index:
                opening_index_slices.append(opening_index)
                opening_price_slices.append(opening_price)

        wpct = calc_wpct(buy_prices, sell_prices)
        _return = (money - init_money) / init_money * 100
        max_drawdown = max(drawdowns)

        return wpct, _return, max_drawdown, \
               opens, closes, highs, lows, volumes, dates, \
               opening_index_slices, opening_price_slices, \
               closing_index_slices, closing_price_slices

    def choose(self, code):
        dates, opens, closes, highs, lows, volumes, ma_price, ma_volume = \
            get_latest_batch_data(code)
        fast_ma = self.calc_fast_ma(closes)
        slow_ma = self.calc_slow_ma(closes)
        fast_mav = self.calc_fast_mav(volumes)
        slow_mav = self.calc_slow_mav(volumes)
        macd, dif, dea = self.macd.calc_macd(closes)

        if (fast_ma[-self.k] < slow_ma[-self.k] and fast_ma[-1] > slow_ma[-1]) \
                and (fast_mav[-self.k] < slow_mav[-self.k] \
                     and fast_mav[-1] > slow_mav[-1]) \
                and (macd[-self.k] < 0 and macd[-1] > 0):
            return True
        else:
            return False


class TripleGoldenCrossBacktest(QThread):
    progress_signal = Signal(int, str, str, float, float, float)

    def __init__(self, stocks, s_date, e_date, init_money, fee, pass_fee, tax,
                 parent=None):
        super(TripleGoldenCrossBacktest, self).__init__(parent)
        self.codes = []
        self.names = []
        self.s_date = datetime.datetime.strptime(s_date, '%Y-%m-%d')
        self.e_date = datetime.datetime.strptime(e_date, '%Y-%m-%d')
        self.init_money = init_money
        self.fee = fee
        self.pass_fee = pass_fee
        self.tax = tax
        for stock in stocks:
            self.codes.append(stock['code'])
            self.names.append(stock['name'])

    def run(self):
        triple_golden_cross = TripleGoldenCross()

        step = int(len(self.codes) / 100) + 1
        i = 0
        j = 0
        for code in self.codes:
            i += 1
            wpct, _return, max_drawdown, \
            opens, closes, highs, lows, volumes, dates, \
            opening_index_slices, opening_price_slices, \
            closing_index_slices, closing_price_slices = \
                triple_golden_cross.backtest(code, self.s_date, self.e_date,
                                             self.init_money,
                                             self.fee, self.pass_fee, self.tax)
            self.progress_signal.emit(j, code, self.names[i - 1],
                                      wpct, _return, max_drawdown)
            if i % step == 0:
                j += 1
        self.progress_signal.emit(100, '', '', 0.0, 0.0, 0.0)


class TripleGoldenCrossChoose(QThread):
    progress_signal = Signal(int, str, str)

    def __init__(self, stocks, parent=None):
        super(TripleGoldenCrossChoose, self).__init__(parent)
        self.codes = []
        self.names = []
        for stock in stocks:
            self.codes.append(stock['code'])
            self.names.append(stock['name'])

    def run(self):
        triple_golden_cross = TripleGoldenCross()

        step = int(len(self.codes) / 100) + 1
        i = 0
        j = 0
        for code in self.codes:
            i += 1
            ret = triple_golden_cross.choose(code)
            if not ret:
                continue
            self.progress_signal.emit(j, code, self.names[i - 1])
            if i % step == 0:
                j += 1
        self.progress_signal.emit(100, '', '')


# TODO: line color
class TripleGoldenCrossConfig(QDialog):
    def __init__(self, parent=None):
        super(TripleGoldenCrossConfig, self).__init__(parent)
        self.setWindowTitle('三金叉策略配置')
        self.setWindowModality(Qt.WindowModal)

        self.config_path = strategies_config_path.joinpath(
            'triple_golden_cross.json')
        self.info = TripleGoldenCrossInfo()

        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.m = data['m']
                self.n = data['n']
                self.k = data['k']
        else:
            self.m = 5
            self.n = 10
            self.k = 5

        reg = QRegExp('[0-9]+$')
        validator = QRegExpValidator()
        validator.setRegExp(reg)

        main_f_box = QFormLayout()
        self.desc = QTextEdit()
        self.desc.setReadOnly(True)
        self.desc.setText(self.info.desc)
        self.fast_period_label = QLabel('周期m')
        self.fast_period_input = QLineEdit(str(self.m))
        self.fast_period_input.setValidator(validator)
        self.slow_period_label = QLabel('周期n')
        self.slow_period_input = QLineEdit(str(self.n))
        self.slow_period_input.setValidator(validator)
        self.period_label = QLabel('周期k')
        self.period_input = QLineEdit(str(self.k))
        self.period_input.setValidator(validator)
        self.btn_cancel = QPushButton('取消')
        self.btn_ok = QPushButton('确定')
        main_f_box.addRow(self.desc)
        main_f_box.addRow(self.fast_period_label, self.fast_period_input)
        main_f_box.addRow(self.slow_period_label, self.slow_period_input)
        main_f_box.addRow(self.period_label, self.period_input)
        main_f_box.addRow(self.btn_cancel, self.btn_ok)
        self.setLayout(main_f_box)

        self.btn_cancel.clicked.connect(self.close)
        self.btn_ok.clicked.connect(self.ok)

    def ok(self):
        if not self.config_path.exists():
            data = {}
        else:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        data['m'] = int(self.fast_period_input.text())
        data['n'] = int(self.slow_period_input.text())
        data['k'] = int(self.period_input.text())
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        self.close()


if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)
    main = TripleGoldenCrossConfig()
    main.show()

    sys.exit(app.exec_())
