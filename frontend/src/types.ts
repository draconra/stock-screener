export interface Stock {
    ticker: string;
    name: string;
    close: number;
    change: number;
    volume: number;
    relative_volume_10d_calc: number;
    RSI: number;
    signal: string;
    sector: string;
    buy_low: number;
    buy_high: number;
    sell_low: number;
    sell_high: number;
    update_time?: number;
}

export interface GroupedStocks {
    [sector: string]: Stock[];
}
