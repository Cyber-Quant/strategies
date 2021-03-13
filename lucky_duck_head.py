import datetime
import json

from qtpy.QtWidgets import *
from qtpy.QtGui import *
from qtpy.QtCore import *

from conf.conf import strategies_config_path
from strategies.common import calc_batch_ma, calc_batch_mav, calc_wpct, \
    get_latest_batch_data


class LuckyDuckHeadInfo:
    def __init__(self):
        self.name = '老鸭头'
        self.desc = '''
        5(m)日线在10(n)日线上形成鸭颈，此期间放量(k)倍。
        然后5日线下穿10日线，形成鸭头，此期间缩量(k)倍。
        接着5日线再次上穿10日线，形成鸭鼻孔，如同时MACD金叉，此时是买入点。
        整个过程不可下穿60(j)日线。
        '''
        self.choose_flag = True
        self.watch_flag = False


class LuckyDuckHead:
    def __init__(self):
        self.config_path = strategies_config_path.joinpath(
            'lucky_duck_head.json')
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.m = data['m']
                self.n = data['n']
                self.k = data['k']
                self.j = data['j']
        else:
            self.m = 5
            self.n = 10
            self.k = 2
            self.j = 60

    def calc_base_ma(self, close):
        ma = [0] * self.j
        ma += calc_batch_ma(close, self.j)
        return ma

    def calc_fast_ma(self, close):
        ma = [0] * self.m
        ma += calc_batch_ma(close, self.m)
        return ma

    def calc_slow_ma(self, close):
        ma = [0] * self.n
        ma += calc_batch_ma(close, self.n)
        return ma

    def calc_fast_mav(self, volume):
        mav = [0] * self.m
        mav += calc_batch_mav(volume, self.m)
        return mav

    def calc_slow_mav(self, volume):
        mav = [0] * self.n
        mav += calc_batch_mav(volume, self.n)
        return mav

    def _backtest(self, fast_ma, slow_ma, base_ma, volumes, state):
        r_fast_ma = fast_ma[::-1]
        r_slow_ma = slow_ma[::-1]
        r_base_ma = base_ma[::-1]
        r_vol = volumes[::-1]

        if r_base_ma[0] < r_fast_ma[0] < r_slow_ma[0] \
                and r_base_ma[1] < r_slow_ma[1] <= r_fast_ma[1] \
                and (r_vol[0] <= r_vol[1] / self.k
                     or r_vol[0] <= r_vol[2] / self.k):
            return 'b'
        elif state == 'b' and r_fast_ma[0] <= r_slow_ma[0]:
            return 's'

    def backtest(self, code, s_date, e_date, init_money, fee, pass_fee, tax):
        dates, opens, closes, highs, lows, volumes, amount, turn, pct_chg, \
        ma_price, mv_volume = get_latest_batch_data(code, s_date=s_date,
                                                    e_date=e_date)
        fast_ma = self.calc_fast_ma(closes)
        slow_ma = self.calc_slow_ma(closes)
        base_ma = self.calc_base_ma(closes)

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

            _fast_ma = fast_ma[i - self.m - self.n:i]
            _slow_ma = slow_ma[i - self.m - self.n:i]
            _base_ma = base_ma[i - self.m - self.n:i]
            _volumes = volumes[i - self.m - self.n:i]
            ret = self._backtest(_fast_ma, _slow_ma, _base_ma,
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
        r_fast_ma = self.calc_fast_ma(closes)[::-1]
        r_slow_ma = self.calc_slow_ma(closes)[::-1]
        r_base_ma = self.calc_base_ma(closes)[::-1]
        r_vol = volumes[::-1]

        if len(closes) < self.n + self.m:
            return False

        if r_base_ma[0] < r_fast_ma[0] < r_slow_ma[0] \
                and r_base_ma[1] < r_slow_ma[1] <= r_fast_ma[1] \
                and (r_vol[0] <= r_vol[1] / self.k
                     or r_vol[0] <= r_vol[2] / self.k):
            return True
        return False


class LuckyDuckHeadBacktest(QThread):
    progress_signal = Signal(int, str, str, float, float, float)

    def __init__(self, stocks, s_date, e_date, init_money, fee, pass_fee, tax,
                 parent=None):
        super(LuckyDuckHeadBacktest, self).__init__(parent)
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
        lucky_duck_head = LuckyDuckHead()

        step = int(len(self.codes) / 100) + 1
        i = 0
        j = 0
        for code in self.codes:
            i += 1
            wpct, _return, max_drawdown, \
            opens, closes, highs, lows, volumes, dates, \
            opening_index_slices, opening_price_slices, \
            closing_index_slices, closing_price_slices = \
                lucky_duck_head.backtest(code, self.s_date, self.e_date,
                                         self.init_money,
                                         self.fee, self.pass_fee, self.tax)
            self.progress_signal.emit(j, code, self.names[i - 1],
                                      wpct, _return, max_drawdown)
            if i % step == 0:
                j += 1
        self.progress_signal.emit(100, '', '', 0.0, 0.0, 0.0)


class LuckyDuckHeadChoose(QThread):
    progress_signal = Signal(int, str, str)

    def __init__(self, stocks, parent=None):
        super(LuckyDuckHeadChoose, self).__init__(parent)
        self.codes = []
        self.names = []
        for stock in stocks:
            self.codes.append(stock['code'])
            self.names.append(stock['name'])

    def run(self):
        lucky_duck_head = LuckyDuckHead()

        step = int(len(self.codes) / 100) + 1
        i = 0
        j = 0
        for code in self.codes:
            i += 1
            ret = lucky_duck_head.choose(code)
            if not ret:
                continue
            self.progress_signal.emit(j, code, self.names[i - 1])
            if i % step == 0:
                j += 1
        self.progress_signal.emit(100, '', '')


# TODO: line color
class LuckyDuckHeadConfig(QDialog):
    def __init__(self, parent=None):
        super(LuckyDuckHeadConfig, self).__init__(parent)
        self.setWindowTitle('老鸭头策略配置')
        self.setWindowModality(Qt.WindowModal)

        self.config_path = strategies_config_path.joinpath(
            'lucky_duck_head.json')
        self.info = LuckyDuckHeadInfo()

        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.m = data['m']
                self.n = data['n']
                self.k = data['k']
                self.j = data['j']
        else:
            self.m = 5
            self.n = 10
            self.k = 2
            self.j = 60

        reg = QRegExp('[0-9]+$')
        validator = QRegExpValidator()
        validator.setRegExp(reg)

        main_f_box = QFormLayout()
        self.desc = QTextEdit()
        self.desc.setReadOnly(True)
        self.desc.setText(self.info.desc)
        self.m_label = QLabel('快速均线周期m')
        self.m_input = QLineEdit(str(self.m))
        self.m_input.setValidator(validator)
        self.n_label = QLabel('慢速均线周期n')
        self.n_input = QLineEdit(str(self.n))
        self.n_input.setValidator(validator)
        self.k_label = QLabel('k倍成交量')
        self.k_input = QLineEdit(str(self.k))
        self.k_input.setValidator(validator)
        self.j_label = QLabel('基线周期j')
        self.j_input = QLineEdit(str(self.j))
        self.j_input.setValidator(validator)
        self.btn_cancel = QPushButton('取消')
        self.btn_ok = QPushButton('确定')
        main_f_box.addRow(self.desc)
        main_f_box.addRow(self.m_label, self.m_input)
        main_f_box.addRow(self.n_label, self.n_input)
        main_f_box.addRow(self.k_label, self.k_input)
        main_f_box.addRow(self.j_label, self.j_input)
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
        data['j'] = int(self.j_input.text())
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        self.close()


if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)
    main = LuckyDuckHeadConfig()
    main.show()

    sys.exit(app.exec_())
