import React, { useEffect, useRef } from 'react';
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts';
import { API_BASE } from '../config';

interface TVChartProps {
    symbol: string;
}

// Signal marker from the backend (includes price zones)
interface SignalMarker {
    time: string;
    position: string;
    color: string;
    shape: string;
    text: string;
    buy_low?: number;
    buy_high?: number;
    sell_low?: number;
    sell_high?: number;
}

// Colors for the price zone lines
const BUY_ZONE_COLOR = 'rgba(38, 166, 154, 0.6)';    // teal
const BUY_ZONE_BG = 'rgba(38, 166, 154, 0.06)';
const SELL_ZONE_COLOR = 'rgba(239, 83, 80, 0.6)';     // red
const SELL_ZONE_BG = 'rgba(239, 83, 80, 0.06)';

const TVChart: React.FC<TVChartProps> = ({ symbol }) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<any>(null);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        const container = chartContainerRef.current;
        const chart = createChart(container, {
            layout: {
                background: { color: '#161b22' },
                textColor: '#d1d4dc',
            },
            grid: {
                vertLines: { color: '#21262d' },
                horzLines: { color: '#21262d' },
            },
            width: container.clientWidth || 600,
            height: container.clientHeight || 400,
            timeScale: {
                borderColor: '#30363d',
            },
            rightPriceScale: {
                borderColor: '#30363d',
            },
            crosshair: {
                horzLine: { color: '#8b949e' },
                vertLine: { color: '#8b949e' },
            },
        });

        const candleSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        chartRef.current = { chart, candleSeries };

        const ro = new ResizeObserver((entries) => {
            for (const entry of entries) {
                const { width, height } = entry.contentRect;
                chart.applyOptions({ width, height });
            }
        });
        ro.observe(container);

        return () => {
            ro.disconnect();
            chart.remove();
        };
    }, []);

    useEffect(() => {
        const fetchData = async () => {
            if (!chartRef.current || !symbol) return;
            const { chart, candleSeries } = chartRef.current;

            try {
                const response = await fetch(`${API_BASE}/api/history/${symbol}`);
                const result = await response.json();

                if (result.status === 'success' && result.data?.length) {
                    candleSeries.setData(result.data);

                    // Create markers using v5 API
                    if (result.markers?.length) {
                        const markersPrimitive = createSeriesMarkers(candleSeries, result.markers);
                        chartRef.current.markersPrimitive = markersPrimitive;

                        // Draw buy/sell price zones for the LAST signal
                        drawPriceZones(chart, candleSeries, result.markers);
                    }

                    chart.timeScale().fitContent();
                }
            } catch (error) {
                console.error('Error fetching chart data:', error);
            }
        };

        fetchData();
    }, [symbol]);

    return (
        <div
            ref={chartContainerRef}
            style={{
                width: '100%',
                height: '100%',
                position: 'relative',
                minHeight: '400px',
            }}
        />
    );
};

/**
 * Draw horizontal price lines for the most recent signal's buy/sell zones.
 * Uses lightweight-charts' createPriceLine API on the candle series.
 */
function drawPriceZones(
    _chart: any,
    candleSeries: any,
    markers: SignalMarker[],
) {
    // Remove any previously drawn price lines
    if (chartPriceLines.length > 0) {
        for (const line of chartPriceLines) {
            try { candleSeries.removePriceLine(line); } catch { /* noop */ }
        }
        chartPriceLines.length = 0;
    }

    // Find the most recent non-SELL signal (buy signals are actionable)
    const lastSignal = [...markers]
        .reverse()
        .find(m => m.buy_low && m.buy_low > 0 && m.text !== 'SELL');

    if (!lastSignal) return;

    const { buy_low, buy_high, sell_low, sell_high, text } = lastSignal;

    // Buy zone lines
    if (buy_low && buy_low > 0) {
        chartPriceLines.push(
            candleSeries.createPriceLine({
                price: buy_low,
                color: BUY_ZONE_COLOR,
                lineWidth: 1,
                lineStyle: 2, // Dashed
                axisLabelVisible: true,
                title: `Buy Low`,
                lineVisible: true,
            })
        );
    }

    if (buy_high && buy_high > 0 && buy_high !== buy_low) {
        chartPriceLines.push(
            candleSeries.createPriceLine({
                price: buy_high,
                color: BUY_ZONE_COLOR,
                lineWidth: 1,
                lineStyle: 2, // Dashed
                axisLabelVisible: true,
                title: `Buy High`,
                lineVisible: true,
            })
        );
    }

    // Sell / target zone lines
    if (sell_low && sell_low > 0) {
        chartPriceLines.push(
            candleSeries.createPriceLine({
                price: sell_low,
                color: SELL_ZONE_COLOR,
                lineWidth: 1,
                lineStyle: 2, // Dashed
                axisLabelVisible: true,
                title: `Target Low`,
                lineVisible: true,
            })
        );
    }

    if (sell_high && sell_high > 0 && sell_high !== sell_low) {
        chartPriceLines.push(
            candleSeries.createPriceLine({
                price: sell_high,
                color: SELL_ZONE_COLOR,
                lineWidth: 1,
                lineStyle: 2, // Dashed
                axisLabelVisible: true,
                title: `Target High`,
                lineVisible: true,
            })
        );
    }
}

// Module-level array to track price lines so we can remove them on refresh
const chartPriceLines: any[] = [];

export default TVChart;
