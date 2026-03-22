import os

import streamlit as st
from streamlit_monaco import st_monaco

from strategy_editor_utils import DATA_DIR, validate_strategy

st.set_page_config(layout="wide")
st.title("Add strategy")
st.write("NOTE: Once you save a strategy you cannot edit it!")

file_name = st.text_input("File name (without extension)")

default_code = """
\"\"\"
This is an example strategy for buying and holding at a specific threshold.

Every 10th of a second, the strategy function runs and you're provided with a LiveMarketState object with the following data:

@dataclass
class LiveMarketState:

    @dataclass
    class EstimatedPrice:
        up: float  # the estimated price you would pay to buy $10 worth of "Up".
        down: float   # the estimated price you would pay to buy $10 worth of "Down".

    @dataclass
    class Btc5MinClobs:
        up: str  # the Polymarket crypto token ID for buying the "Up" direction in this market.
        down: str # the Polymarket crypto token ID for buying the "Down" direction in this market.

    slug: str  # the browser URL slug for the current BTC 5-min market.
    start_ts: int  # the start timestamp of the current BTC 5-min market.
    start_EST: str  # an Eastern Time Zone formatted string of the start time of the market. 
    elapsed_seconds: int  # the number of seconds the market has been live from 0 to 300.

    price: EstimatedPrice
    clobs: Btc5MinClobs  # Polymarket internal API ids.
    trades: list[Trade] = field(default_factory=list)  # Any previous traes made by this strategy will show up on subsequent runs in here.

When you make a trade, it needs to be an instance of this object:

@dataclass
class Trade:

    class Side(Enum):
        BUY = "buy"
        SELL = "sell"

    class Outcome(Enum):
        UP = "up"
        DOWN = "down"

    outcome: Outcome
    clob: str  # MAKE SURE THIS MATCHES THE CORRECT DIRECTION!!!!!
    side: Side
    amount: float
    price: float

    # the current datetime timestamp for logging
    dt: float


\"\"\"


def run_strategy(state: LiveMarketState) -> Strategy.Result:

    def get_window():
        # This is the time-window for executing the strategy (in seconds).
        if state.elapsed_seconds < 180:
            return "before"
        elif state.elapsed_seconds >= 180 and state.elapsed_seconds < 300:
            return "can_trigger"
        else:
            return "after"

    def in_buy_threshold(price: float, min=0.95, max=0.985) -> bool:
        # This determines at what price to buy (initially).
        return price >= min and price <= max

    def get_buy_amount():
        # How much to buy (initially). Right now just hardcoded at 10. In the future "state" will track
        # the amount of cach a strategy has / starts with.
        return 10

    trade = None
    window = get_window()
    if len(state.trades) == 0:
        amount = get_buy_amount()
        if window == "can_trigger":
            if in_buy_threshold(state.price.up):
                trade = Trade(
                    outcome=Trade.Outcome.UP,
                    clob=state.clobs.up,
                    side=Trade.Side.BUY,
                    amount=amount,
                    price=state.price.up,
                    dt=datetime.now().timestamp(),
                )
            elif in_buy_threshold(state.price.down):
                trade = Trade(
                    outcome=Trade.Outcome.DOWN,
                    clob=state.clobs.down,
                    side=Trade.Side.BUY,
                    amount=amount,
                    price=state.price.down,
                    dt=datetime.now().timestamp(),
                )

    return Strategy.Result(trade, {"window": window})

"""

code = st_monaco(
    value=default_code,
    language="python",
    theme="vs-dark",
    height="1000px",
)

if st.button("Save"):
    if not file_name.strip():
        st.error("Please enter a file name")
    else:
        err = validate_strategy(code)
        if err:
            st.error(f"Strategy rejected: {err}")
        else:
            full_name = f"{file_name}.py"
            path = os.path.join(DATA_DIR, full_name)
            if os.path.exists(path):
                st.error("File already exists ❌")
            else:
                with open(path, "w") as f:
                    f.write(code)
                st.success(f"Saved {full_name} ✅")
