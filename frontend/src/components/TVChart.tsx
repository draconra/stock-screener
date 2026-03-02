import React, { useEffect, useRef } from 'react';
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts';

interface TVChartProps {
    symbol: string;
}

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
                const response = await fetch(`http://localhost:8000/api/history/${symbol}`);
                const result = await response.json();

                if (result.status === 'success' && result.data?.length) {
                    candleSeries.setData(result.data);

                    // Create markers using v5 API
                    if (result.markers?.length) {
                        const markersPrimitive = createSeriesMarkers(candleSeries, result.markers);
                        // Store reference so we can update later if needed
                        chartRef.current.markersPrimitive = markersPrimitive;
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

export default TVChart;
