import React, { useEffect, useRef } from 'react';
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts';
import { API_BASE } from '../config';

interface TVChartProps {
    symbol: string;
}

const WEEK_BARS = 5; // trading days in 1 week

const TVChart: React.FC<TVChartProps> = ({ symbol }) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<any>(null);

    // Create chart instance once on mount
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
                // Show dates clearly at the 1-week scale
                timeVisible: true,
                secondsVisible: false,
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

    // Fetch data and render whenever symbol changes
    useEffect(() => {
        const fetchData = async () => {
            if (!chartRef.current || !symbol) return;
            const { chart, candleSeries } = chartRef.current;

            try {
                const response = await fetch(`${API_BASE}/api/history/${symbol}`);
                const result = await response.json();

                if (result.status === 'success' && result.data?.length) {
                    candleSeries.setData(result.data);

                    // Draw signal markers (arrows) on candles
                    if (result.markers?.length) {
                        createSeriesMarkers(candleSeries, result.markers);
                    }

                    // Zoom the visible range to the last WEEK_BARS trading days
                    const totalBars = result.data.length;
                    const from = Math.max(0, totalBars - WEEK_BARS - 1);
                    const to = totalBars - 1;
                    chart.timeScale().setVisibleLogicalRange({ from, to });
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

export default TVChart;
