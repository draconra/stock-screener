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
}

export interface GroupedStocks {
    [sector: string]: Stock[];
}
