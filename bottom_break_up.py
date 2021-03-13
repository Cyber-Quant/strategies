import datetime
import json

from qtpy.QtWidgets import *
from qtpy.QtGui import *
from qtpy.QtCore import *

from conf.conf import strategies_config_path
from strategies.common import calc_batch_ma, calc_batch_mav, calc_wpct, \
    get_latest_batch_data


class BottomBreakUpInfo:
    def __init__(self):
        self.name = '底部突破'
        self.desc = '''
        20(m)日，均线一直是空头排列
        5(n)个交易日内，10日均线开始放2(k)倍量上穿20日和39日均线，上升趋势形成。
        '''
        self.choose_flag = True
        self.watch_flag = False


class BottomBreakUp:
    def __init__(self):
        self.config_path = strategies_config_path.joinpath(
            'bottom_break_up.json')
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.m = data['m']
                self.n = data['n']
                self.k = data['k']
        else:
            self.m = 20
            self.n = 5
            self.k = 2

    def calc_5_ma(self, close):
        ma = [0] * 5
        ma += calc_batch_ma(close, 5)
        return ma

    def calc_10_ma(self, close):
        ma = [0] * 10
        ma += calc_batch_ma(close, 10)
        return ma

    def calc_20_ma(self, close):
        ma = [0] * 20
        ma += calc_batch_ma(close, 20)
        return ma

    def calc_30_ma(self, close):
        ma = [0] * 30
        ma += calc_batch_ma(close, 30)
        return ma

    def calc_60_ma(self, close):
        ma = [0] * 60
        ma += calc_batch_ma(close, 60)
        return ma

    def calc_mav(self, volume, period):
        mav = calc_batch_mav(volume, period)
        _mav = [0] * period
        mav = _mav + mav
        return mav

    def _backtest(self, ma_10, ma_20, ma_30, ma_60, volumes, state):
        r_ma_10 = ma_10[::-1]
        r_ma_20 = ma_20[::-1]
        r_ma_30 = ma_30[::-1]
        r_ma_60 = ma_60[::-1]
        r_vol = volumes[::-1]

        fall_flag = False
        for i in range(self.m):
            if r_ma_60[self.n + i] > r_ma_30[self.n + i] > r_ma_20[self.n + i]:
                fall_flag = True
            elif state == 'b' and r_ma_10[0] <= r_ma_30[0] \
                    and r_ma_10[0] <= r_ma_20[0]:
                return 's'
            else:
                fall_flag = False

        break_up_flag = False
        for j in range(self.n):
            if r_ma_10[j] > r_ma_20[j] \
                    and r_vol[j] >= 2 * r_vol[j + 1] \
                    and j < self.n - 1:
                break_up_flag = True
            else:
                break_up_flag = False

        return fall_flag and break_up_flag

    def backtest(self, code, s_date, e_date, init_money, fee, pass_fee, tax):
        dates, opens, closes, highs, lows, volumes, amount, turn, pct_chg, \
        ma_price, mv_volume = get_latest_batch_data(code, s_date=s_date,
                                                    e_date=e_date)
        ma_10 = self.calc_10_ma(closes)
        ma_20 = self.calc_20_ma(closes)
        ma_30 = self.calc_30_ma(closes)
        ma_60 = self.calc_60_ma(closes)

        start = self.m + self.n
        buy_prices = []
        buy_dates = []
        buy_index = []
        sell_prices = []
        sell_dates = []
        sell_index = []
        drawdowns = []
        old_state = 's'
        for i in range(len(closes)):
            if i < start:
                continue

            _ma_10 = ma_10[i - self.m - self.n:i]
            _ma_20 = ma_20[i - self.m - self.n:i]
            _ma_30 = ma_30[i - self.m - self.n:i]
            _ma_60 = ma_60[i - self.m - self.n:i]
            _volumes = volumes[i - self.m - self.n:i]
            ret = self._backtest(_ma_10, _ma_20, _ma_30, _ma_60,
                                 _volumes, old_state)
            if ret == 'b':
                state = 'b'
                if state != old_state:
                    buy_prices.append(closes[i])
                    buy_dates.append(dates[i])
                    buy_index.append(i)
                    old_state = state
            elif ret == 's':
                state = 's'
                if state != old_state:
                    sell_prices.append(closes[i])
                    sell_dates.append(dates[i])
                    sell_index.append(i)
                    old_state = state
            else:
                continue

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
        dates, opens, closes, highs, lows, volumes, amount, turn, pct_chg, \
        ma_price, ma_volume = get_latest_batch_data(code)
        r_ma_10 = self.calc_10_ma(closes)[::-1]
        r_ma_20 = self.calc_20_ma(closes)[::-1]
        r_ma_30 = self.calc_30_ma(closes)[::-1]
        r_ma_60 = self.calc_60_ma(closes)[::-1]
        r_vol = volumes[::-1]

        if len(closes) < self.n + self.m:
            return False

        fall_flag = False
        for i in range(self.m):
            if r_ma_60[self.n + i] > r_ma_30[self.n + i] > r_ma_20[self.n + i]:
                fall_flag = True
            else:
                fall_flag = False

        break_up_flag = False
        for j in range(self.n):
            if r_ma_10[j] > r_ma_20[j] \
                    and r_vol[j] >= 2 * r_vol[j + 1] \
                    and j < self.n - 1:
                break_up_flag = True
            else:
                break_up_flag = False

        return fall_flag and break_up_flag


class BottomBreakUpBacktest(QThread):
    progress_signal = Signal(int, str, str, float, float, float)

    def __init__(self, stocks, s_date, e_date, init_money, fee, pass_fee, tax,
                 parent=None):
        super(BottomBreakUpBacktest, self).__init__(parent)
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
        bottom_break_up = BottomBreakUp()

        step = int(len(self.codes) / 100) + 1
        i = 0
        j = 0
        for code in self.codes:
            i += 1
            wpct, _return, max_drawdown, \
            opens, closes, highs, lows, volumes, dates, \
            opening_index_slices, opening_price_slices, \
            closing_index_slices, closing_price_slices = \
                bottom_break_up.backtest(code, self.s_date, self.e_date,
                                         self.init_money,
                                         self.fee, self.pass_fee, self.tax)
            self.progress_signal.emit(j, code, self.names[i - 1],
                                      wpct, _return, max_drawdown)
            if i % step == 0:
                j += 1
        self.progress_signal.emit(100, '', '', 0.0, 0.0, 0.0)


class BottomBreakUpChoose(QThread):
    progress_signal = Signal(int, str, str)

    def __init__(self, stocks, parent=None):
        super(BottomBreakUpChoose, self).__init__(parent)
        self.codes = []
        self.names = []
        for stock in stocks:
            self.codes.append(stock['code'])
            self.names.append(stock['name'])

    def run(self):
        bottom_break_up = BottomBreakUp()

        step = int(len(self.codes) / 100) + 1
        i = 0
        j = 0
        for code in self.codes:
            i += 1
            ret = bottom_break_up.choose(code)
            if not ret:
                continue
            self.progress_signal.emit(j, code, self.names[i - 1])
            if i % step == 0:
                j += 1
        self.progress_signal.emit(100, '', '')


# TODO: line color
class BottomBreakUpConfig(QDialog):
    def __init__(self, parent=None):
        super(BottomBreakUpConfig, self).__init__(parent)
        self.setWindowTitle('底部突破策略配置')
        self.setWindowModality(Qt.WindowModal)

        self.config_path = strategies_config_path.joinpath(
            'bottom_break_up.json')
        self.info = BottomBreakUpInfo()

        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.m = data['m']
                self.n = data['n']
                self.k = data['k']
        else:
            self.m = 20
            self.n = 5
            self.k = 2

        reg = QRegExp('[0-9]+$')
        validator = QRegExpValidator()
        validator.setRegExp(reg)

        main_f_box = QFormLayout()
        self.desc = QTextEdit()
        self.desc.setReadOnly(True)
        self.desc.setText(self.info.desc)
        self.m_label = QLabel('连续m日')
        self.m_input = QLineEdit(str(self.m))
        self.m_input.setValidator(validator)
        self.n_label = QLabel('n日内')
        self.n_input = QLineEdit(str(self.n))
        self.n_input.setValidator(validator)
        self.k_label = QLabel('k倍成交量')
        self.k_input = QLineEdit(str(self.k))
        self.k_input.setValidator(validator)
        self.btn_cancel = QPushButton('取消')
        self.btn_ok = QPushButton('确定')
        main_f_box.addRow(self.desc)
        main_f_box.addRow(self.m_label, self.m_input)
        main_f_box.addRow(self.n_label, self.n_input)
        main_f_box.addRow(self.k_label, self.k_input)
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
        data['m'] = int(self.m_input.text())
        data['n'] = int(self.n_input.text())
        data['k'] = int(self.k_input.text())
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        self.close()


if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)
    main = BottomBreakUpConfig()
    main.show()

    sys.exit(app.exec_())
