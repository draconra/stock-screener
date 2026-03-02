import React, { useState } from 'react';
import { Search, ChevronDown, ChevronUp } from 'lucide-react';

interface GlossaryEntry {
    term: string;
    short: string;
    detail: string;
    category: string;
}

const entries: GlossaryEntry[] = [
    {
        term: 'RSI (Relative Strength Index)',
        short: 'Indikator momentum yang mengukur kecepatan perubahan harga.',
        detail: 'RSI bergerak antara 0–100. Jika RSI di atas 70, saham dianggap overbought (jenuh beli) dan berpotensi turun. Jika di bawah 30, saham dianggap oversold (jenuh jual) dan berpotensi naik. Di aplikasi ini, RSI digunakan untuk menentukan sinyal BUY dan STRONG BUY.',
        category: 'Indikator',
    },
    {
        term: 'EMA (Exponential Moving Average)',
        short: 'Rata-rata pergerakan harga yang lebih responsif terhadap harga terbaru.',
        detail: 'EMA memberi bobot lebih besar pada harga terkini dibanding SMA (Simple Moving Average). Aplikasi ini menggunakan EMA9 (jangka pendek), EMA21 (jangka menengah), dan EMA50 (jangka panjang). Ketika EMA9 di atas EMA21, artinya tren jangka pendek sedang naik (bullish).',
        category: 'Indikator',
    },
    {
        term: 'ATR (Average True Range)',
        short: 'Ukuran rata-rata volatilitas (gejolak) harga saham.',
        detail: 'ATR menghitung rata-rata rentang pergerakan harga harian. Semakin tinggi ATR, semakin besar potensi pergerakan harga. Di aplikasi ini, ATR digunakan untuk menghitung zona beli (buy range) dan target jual (sell target) secara dinamis.',
        category: 'Indikator',
    },
    {
        term: 'Bollinger Bands',
        short: 'Pita di atas dan bawah harga yang menunjukkan batas volatilitas.',
        detail: 'Terdiri dari 3 garis: garis tengah (SMA20), pita atas (SMA20 + 2 standar deviasi), dan pita bawah (SMA20 - 2 standar deviasi). Ketika harga menyentuh pita bawah, sering dianggap murah. Ketika menyentuh pita atas, dianggap mahal.',
        category: 'Indikator',
    },
    {
        term: 'Stochastic',
        short: 'Indikator yang membandingkan harga penutupan dengan rentang harga tertentu.',
        detail: 'Stochastic mengukur posisi harga penutupan relatif terhadap rentang high-low dalam periode tertentu (biasanya 14 hari). Nilai di atas 80 menandakan overbought, di bawah 20 menandakan oversold. Berguna untuk mengkonfirmasi sinyal dari indikator lain.',
        category: 'Indikator',
    },
    {
        term: 'RVOL (Relative Volume)',
        short: 'Perbandingan volume saat ini dengan rata-rata volume 10 hari.',
        detail: 'RVOL 2.0x berarti volume hari ini 2 kali lipat dari rata-rata. Volume tinggi menandakan banyak trader yang aktif, sehingga pergerakan harga lebih terpercaya. Di aplikasi ini, RVOL > 1.2x menjadi syarat minimum untuk masuk daftar screener.',
        category: 'Volume',
    },
    {
        term: 'Volume',
        short: 'Jumlah saham yang diperdagangkan dalam satu periode.',
        detail: 'Volume adalah bahan bakar pergerakan harga. Kenaikan harga dengan volume besar lebih kuat daripada kenaikan tanpa volume. Penurunan harga dengan volume kecil bisa jadi hanya koreksi sementara.',
        category: 'Volume',
    },
    {
        term: 'STRONG BUY',
        short: 'Sinyal beli kuat berdasarkan kombinasi tren, RSI, dan volume.',
        detail: 'Sinyal STRONG BUY muncul ketika: EMA9 > EMA21 (tren naik), RSI antara 35–55 (belum overbought), dan RVOL > 2.5x (volume sangat tinggi). Ini menandakan momentum beli yang kuat dengan risiko pullback yang relatif kecil.',
        category: 'Sinyal',
    },
    {
        term: 'BUY',
        short: 'Sinyal beli berdasarkan tren naik dan volume di atas rata-rata.',
        detail: 'Sinyal BUY muncul ketika: EMA9 > EMA21 (tren naik), RSI antara 30–60, dan RVOL > 1.5x. Sinyal ini lebih umum dari STRONG BUY dan menandakan peluang beli yang layak dipertimbangkan.',
        category: 'Sinyal',
    },
    {
        term: 'WATCH',
        short: 'Saham yang perlu dipantau, belum memenuhi kriteria beli.',
        detail: 'Saham dengan sinyal WATCH masuk radar karena volume tinggi (RVOL > 1.2x), tetapi belum memenuhi kriteria RSI atau tren untuk sinyal BUY. Pantau terus untuk peluang masuk di waktu yang tepat.',
        category: 'Sinyal',
    },
    {
        term: 'Buy Range (Zona Beli)',
        short: 'Rentang harga yang disarankan untuk membeli saham.',
        detail: 'Buy range dihitung berdasarkan ATR, EMA21, Bollinger Band bawah, dan Pivot S1. Angka bawah adalah area support terdekat, angka atas biasanya mendekati harga saat ini. Beli di rentang ini memberikan rasio risk-reward yang lebih baik.',
        category: 'Harga',
    },
    {
        term: 'Sell Target (Target Jual)',
        short: 'Rentang harga target untuk mengambil keuntungan.',
        detail: 'Sell target dihitung dari kelipatan ATR di atas harga beli. Target rendah untuk pengambilan keuntungan sebagian, target tinggi untuk memaksimalkan keuntungan. Target dibatasi oleh resistance Pivot R1 bulanan.',
        category: 'Harga',
    },
    {
        term: 'Pivot Point',
        short: 'Level harga penting yang dihitung dari data harga sebelumnya.',
        detail: 'Pivot point menghitung level support (S1, S2) dan resistance (R1, R2) dari harga High, Low, dan Close periode sebelumnya. Trader menggunakan level ini sebagai acuan untuk menentukan target harga dan level stop loss.',
        category: 'Harga',
    },
    {
        term: 'Support',
        short: 'Level harga di mana saham cenderung berhenti turun.',
        detail: 'Support adalah level harga di mana permintaan (buyer) cukup kuat untuk menahan penurunan harga. Ketika harga mendekati support, sering terjadi pantulan ke atas. Jika support ditembus (breakdown), harga bisa turun lebih jauh.',
        category: 'Harga',
    },
    {
        term: 'Resistance',
        short: 'Level harga di mana saham cenderung berhenti naik.',
        detail: 'Resistance adalah level harga di mana tekanan jual cukup kuat untuk menahan kenaikan harga. Jika resistance ditembus (breakout) dengan volume besar, harga berpotensi naik signifikan.',
        category: 'Harga',
    },
    {
        term: 'Bullish',
        short: 'Kondisi pasar atau saham yang sedang dalam tren naik.',
        detail: 'Istilah bullish berasal dari serangan banteng yang menyeruduk ke atas. Pasar bullish ditandai dengan harga yang terus naik, volume meningkat, dan sentimen positif dari pelaku pasar.',
        category: 'Umum',
    },
    {
        term: 'Bearish',
        short: 'Kondisi pasar atau saham yang sedang dalam tren turun.',
        detail: 'Istilah bearish berasal dari serangan beruang yang mencakar ke bawah. Pasar bearish ditandai dengan harga yang terus turun dan sentimen negatif.',
        category: 'Umum',
    },
    {
        term: 'Overbought (Jenuh Beli)',
        short: 'Kondisi di mana harga sudah naik terlalu tinggi dan berpotensi koreksi.',
        detail: 'Biasanya ditandai dengan RSI > 70 atau Stochastic > 80. Overbought bukan berarti harus langsung jual, tapi perlu waspada terhadap potensi penurunan harga. Di tren naik kuat, saham bisa tetap overbought untuk waktu yang lama.',
        category: 'Umum',
    },
    {
        term: 'Oversold (Jenuh Jual)',
        short: 'Kondisi di mana harga sudah turun terlalu rendah dan berpotensi rebound.',
        detail: 'Biasanya ditandai dengan RSI < 30 atau Stochastic < 20. Oversold bisa menjadi peluang beli jika didukung oleh volume dan sentimen yang membaik.',
        category: 'Umum',
    },
    {
        term: 'Scalping',
        short: 'Strategi trading jangka sangat pendek untuk meraih keuntungan kecil tapi sering.',
        detail: 'Scalper membeli dan menjual saham dalam hitungan menit hingga jam. Keuntungan per transaksi kecil (0.5–2%), tapi dilakukan berkali-kali. Membutuhkan saham dengan volume tinggi dan spread kecil. Aplikasi ini dirancang untuk membantu scalper IDX.',
        category: 'Umum',
    },
    {
        term: 'Lot',
        short: 'Satuan perdagangan saham di BEI. 1 lot = 100 lembar saham.',
        detail: 'Di Bursa Efek Indonesia, saham diperdagangkan dalam satuan lot. Jika harga saham Rp 1.000 per lembar, maka 1 lot bernilai Rp 100.000. Minimum pembelian adalah 1 lot.',
        category: 'Umum',
    },
    {
        term: 'IHSG (Indeks Harga Saham Gabungan)',
        short: 'Indeks utama yang mencerminkan pergerakan seluruh saham di BEI.',
        detail: 'IHSG adalah barometer utama pasar saham Indonesia. Jika IHSG naik, mayoritas saham cenderung ikut naik. Trader sering melihat arah IHSG sebelum mengambil keputusan trading.',
        category: 'Umum',
    },
    {
        term: 'Volatilitas',
        short: 'Tingkat gejolak atau fluktuasi harga saham.',
        detail: 'Saham dengan volatilitas tinggi bergerak naik-turun dengan cepat, memberikan peluang keuntungan lebih besar tapi juga risiko lebih tinggi. ATR adalah salah satu cara mengukur volatilitas.',
        category: 'Umum',
    },
    {
        term: 'Breakout',
        short: 'Harga menembus level resistance dengan volume besar.',
        detail: 'Breakout terjadi ketika harga berhasil melewati level resistance yang sebelumnya sulit ditembus. Breakout yang disertai volume besar lebih valid dan sering diikuti kenaikan harga yang signifikan.',
        category: 'Umum',
    },
    {
        term: 'Breakdown',
        short: 'Harga menembus level support ke bawah.',
        detail: 'Kebalikan dari breakout. Harga turun melewati level support, menandakan tekanan jual yang kuat. Trader biasanya cut loss jika terjadi breakdown pada saham yang dipegang.',
        category: 'Umum',
    },
    {
        term: 'Cut Loss',
        short: 'Menjual saham rugi untuk membatasi kerugian lebih besar.',
        detail: 'Cut loss adalah disiplin paling penting dalam trading. Biasanya dilakukan jika harga turun 2–5% dari harga beli. Lebih baik rugi kecil daripada menahan saham yang terus turun.',
        category: 'Umum',
    },
    {
        term: 'Take Profit',
        short: 'Menjual saham untuk mengamankan keuntungan yang sudah didapat.',
        detail: 'Take profit sebaiknya dilakukan bertahap. Misalnya, jual 50% di target pertama (sell_low) dan sisanya di target kedua (sell_high). Ini memaksimalkan keuntungan sambil mengamankan profit.',
        category: 'Umum',
    },
    {
        term: 'Spread',
        short: 'Selisih antara harga jual terbaik (offer) dan harga beli terbaik (bid).',
        detail: 'Spread kecil menandakan saham yang likuid dan mudah diperdagangkan. Untuk scalping, pilih saham dengan spread 1–2 tick saja agar biaya transaksi tidak memakan keuntungan.',
        category: 'Umum',
    },
];

const categories = ['Semua', 'Indikator', 'Volume', 'Sinyal', 'Harga', 'Umum'];

export default function GlossaryTab() {
    const [search, setSearch] = useState('');
    const [activeCategory, setActiveCategory] = useState('Semua');
    const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

    const filtered = entries.filter(e => {
        const matchCat = activeCategory === 'Semua' || e.category === activeCategory;
        const matchSearch = !search || e.term.toLowerCase().includes(search.toLowerCase())
            || e.short.toLowerCase().includes(search.toLowerCase());
        return matchCat && matchSearch;
    });

    return (
        <div className="glossary-container">
            <div className="glossary-header">
                <h2 style={{ margin: 0, fontSize: '1.2rem' }}>Kamus Saham</h2>
                <p style={{ margin: '4px 0 0', color: '#8b949e', fontSize: '0.85rem' }}>
                    Panduan istilah trading untuk pemula
                </p>
            </div>

            <div className="glossary-search">
                <Search size={16} color="#8b949e" />
                <input
                    type="text"
                    placeholder="Cari istilah... (contoh: RSI, volume)"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="glossary-search-input"
                />
            </div>

            <div className="glossary-categories">
                {categories.map(cat => (
                    <button
                        key={cat}
                        className={`glossary-cat-btn ${activeCategory === cat ? 'glossary-cat-active' : ''}`}
                        onClick={() => setActiveCategory(cat)}
                    >
                        {cat}
                    </button>
                ))}
            </div>

            <div className="glossary-list">
                {filtered.length === 0 && (
                    <div className="empty-state">Tidak ditemukan istilah yang cocok.</div>
                )}
                {filtered.map((entry, i) => {
                    const globalIdx = entries.indexOf(entry);
                    const isOpen = expandedIdx === globalIdx;
                    return (
                        <div
                            key={globalIdx}
                            className={`glossary-item ${isOpen ? 'glossary-item-open' : ''}`}
                            onClick={() => setExpandedIdx(isOpen ? null : globalIdx)}
                        >
                            <div className="glossary-item-header">
                                <div>
                                    <span className="glossary-term">{entry.term}</span>
                                    <span className="glossary-cat-tag">{entry.category}</span>
                                </div>
                                {isOpen ? <ChevronUp size={16} color="#8b949e" /> : <ChevronDown size={16} color="#8b949e" />}
                            </div>
                            <p className="glossary-short">{entry.short}</p>
                            {isOpen && <p className="glossary-detail">{entry.detail}</p>}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
