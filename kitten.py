import datetime
import json

from qtpy.QtWidgets import *
from qtpy.QtGui import *
from qtpy.QtCore import *

from conf.conf import strategies_config_path
from strategies.common import get_latest_batch_data, calc_batch_ma, calc_wpct


class KittenInfo:
    def __init__(self):
        self.name = '小猫咪超短'
        self.desc = '''
        上升趋势，20(m)日均线，5(n)日连续向上
        出现下跌3(i)-5(k)的个点的阴线
        次日，上涨到达前阴的1/2处或更高，成交量比前阴缩量1/3-1/2，买入。
        买入后出现阴线就卖。
        选股时，出现阴线，即被选中，第二天关注买入时机。
        '''
        self.choose_flag = True
        self.watch_flag = False


class Kitten:
    def __init__(self):
        self.config_path = strategies_config_path.joinpath('kitten.json')
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.m = data['m']
                self.n = data['n']
                self.k = data['k']
        else:
            self.m = 20
            self.n = 5
            self.i = 3
            self.k = 5

    def calc_batch_ma_indicator(self, close):
        ma = [0] * self.m
        ma += calc_batch_ma(close, self.m)
        return ma

    def _backtest(self, mas, opens, closes, volumes, state):
        last_ma = 0
        for _ma in mas[:-1]:
            if _ma > last_ma:
                last_ma = _ma
            else:
                return False

        if 3 <= (closes[-3] - closes[-2]) / closes[-3] * 100 <= 5:
            if closes[-1] > opens[-1] > closes[-2]:
                if closes[-1] > closes[-2] + (opens[-2] - closes[-2]) / 2:
                    if volumes[-2] - volumes[-1] / volumes[-2] < 3:
                        return 'b'
        elif state == 'b' and closes[-1] < opens[-1]:
            return 's'
        else:
            return False

    def backtest(self, code, s_date, e_date, init_money, fee, pass_fee, tax):
        dates, opens, closes, highs, lows, volumes, amount, turn, pct_chg, \
        ma_price, mv_volume = get_latest_batch_data(code, s_date=s_date,
                                                    e_date=e_date)
        mas = self.calc_batch_ma_indicator(closes)
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

            _mas = mas[i - self.n - 1:i]
            _opens = opens[i - self.n - 1:i]
            _closes = closes[i - self.n - 1:i]
            _volumes = volumes[i - self.n - 1:i]
            ret = self._backtest(_mas, _opens, _closes, _volumes, old_state)
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
        ma = calc_batch_ma(closes, self.m)
        last_ma = 0
        for _ma in ma[-self.n:]:
            if _ma > last_ma:
                last_ma = _ma
            else:
                return False

        if len(closes) < 2:
            return False
            
        if 3 <= (closes[-2] - closes[-1]) / closes[-2] * 100 <= 5:
            return True
        else:
            return False


class KittenBacktest(QThread):
    progress_signal = Signal(int, str, str, float, float, float)

    def __init__(self, stocks, s_date, e_date, init_money, fee, pass_fee, tax,
                 parent=None):
        super(KittenBacktest, self).__init__(parent)
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
        kitten = Kitten()

        step = int(len(self.codes) / 100) + 1
        i = 0
        j = 0
        for code in self.codes:
            i += 1
            wpct, _return, max_drawdown, \
            opens, closes, highs, lows, volumes, dates, \
            opening_index_slices, opening_price_slices, \
            closing_index_slices, closing_price_slices = \
                kitten.backtest(code, self.s_date, self.e_date, self.init_money,
                                self.fee, self.pass_fee, self.tax)
            self.progress_signal.emit(j, code, self.names[i - 1],
                                      wpct, _return, max_drawdown)
            if i % step == 0:
                j += 1
        self.progress_signal.emit(100, '', '', 0.0, 0.0, 0.0)


class KittenChoose(QThread):
    progress_signal = Signal(int, str, str)

    def __init__(self, stocks, parent=None):
        super(KittenChoose, self).__init__(parent)
        self.codes = []
        self.names = []
        for stock in stocks:
            self.codes.append(stock['code'])
            self.names.append(stock['name'])

    def run(self):
        kitten = Kitten()

        step = int(len(self.codes) / 100) + 1
        i = 0
        j = 0
        for code in self.codes:
            i += 1
            ret = kitten.choose(code)
            if not ret:
                continue
            self.progress_signal.emit(j, code, self.names[i - 1])
            if i % step == 0:
                j += 1
        self.progress_signal.emit(100, '', '')


# TODO: line color
class KittenConfig(QDialog):
    def __init__(self, parent=None):
        super(KittenConfig, self).__init__(parent)
        self.setWindowTitle('小猫咪交易策略配置')
        self.setWindowModality(Qt.WindowModal)

        self.config_path = strategies_config_path.joinpath('kitten.json')
        self.info = KittenInfo()

        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.m = data['m']
                self.n = data['n']
                self.i = data['i']
                self.k = data['k']
        else:
            self.m = 20
            self.n = 5
            self.i = 3
            self.k = 5

        reg = QRegExp('[0-9]+$')
        validator = QRegExpValidator()
        validator.setRegExp(reg)

        main_f_box = QFormLayout()
        self.desc = QTextEdit()
        self.desc.setReadOnly(True)
        self.desc.setText(self.info.desc)
        self.m_label = QLabel('均线周期m')
        self.m_input = QLineEdit(str(self.m))
        self.m_input.setValidator(validator)
        self.n_label = QLabel('连续n日上涨')
        self.n_input = QLineEdit(str(self.n))
        self.n_input.setValidator(validator)
        self.i_label = QLabel('i个点')
        self.i_input = QLineEdit(str(self.i))
        self.i_input.setValidator(validator)
        self.k_label = QLabel('k个点')
        self.k_input = QLineEdit(str(self.k))
        self.k_input.setValidator(validator)
        self.btn_cancel = QPushButton('取消')
        self.btn_ok = QPushButton('确定')
        main_f_box.addRow(self.desc)
        main_f_box.addRow(self.m_label, self.m_input)
        main_f_box.addRow(self.n_label, self.n_input)
        main_f_box.addRow(self.i_label, self.i_input)
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
        data['i'] = int(self.i_input.text())
        data['k'] = int(self.k_input.text())
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        self.close()


if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)
    main = KittenConfig()
    main.show()

    sys.exit(app.exec_())
