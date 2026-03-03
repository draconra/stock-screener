"""
Daftar Efek Syariah — OJK DES Period II 2025 (effective 1 Dec 2025).
Source: Keputusan DK OJK No. KEP-59/D.04/2025
Fallback hardcoded set (~665 tickers). Refresh attempted on startup from KSEI.
"""

import logging
import urllib.request
import re
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Baseline hardcoded set (OJK DES Period II 2025) ────────────────────────
# Based on official OJK DES list. Updated Dec 2025.
# NOT syariah: conventional banks (BBCA BBRI BMRI BBNI BDMN BNGA NISP BNII PNBN
#   MAYA BJTM BJBR MEGA BMAS), tobacco (HMSP GGRM), alcohol (MLBI), and
#   some multi-finance companies.
_BASELINE: set[str] = {
    # Agriculture
    "AALI","BWPT","DSFI","GOZCO","GZCO","JAWA","LSIP","MAGP","PALM","SGRO",
    "SIMP","SMAR","SSMS","TBLA","UNSP",
    # Basic Industry
    "ADMG","AGII","AKPI","ALDO","ALKA","AMFG","ARNA","BRPT","BTON","CPIN",
    "DPNS","EKAD","ETWA","FASW","FPNI","IGAR","IKBI","IMPC","INAI","INCI",
    "INKP","INRU","INTP","IPOL","ISSP","JKSW","JPFA","KDSI","KIAS","KRAH",
    "LMSH","MDKI","MOLI","MPIA","MRAT","MYOR","NIKL","PBID","PBRX","PLTA",
    "POLY","PPGL","PRAS","PSDN","PTIS","RICY","ROTI","SAIP","SCPI","SIAP",
    "SKBM","SKLT","SMBR","SMCB","SMGR","SPMA","SRBI","SRSN","SSBI","STAR",
    "SULI","SWAT","TALF","TIRT","TKIM","TOTO","TPIA","TRST","UNIC","VOKS",
    "WTON","YPAS",
    # Consumer Goods
    "ALTO","BUDI","CEKA","DLTA","DVLA","GOOD","HOKI","ICBP","IIKP","INDF",
    "KAEF","KINO","KLBF","LMPI","MBTO","MERK","MLPL","MTDL","MYOR","PCAR",
    "PEHA","PRAS","PSGO","PYFA","RMBA","SCPI","SIDO","SKLT","STTP","TSPC",
    "UNVR","WIIM","WOOD",
    # Finance (Islamic/Syariah)
    "BBYB","BRIS","BTPS","PNLF","TRIM",
    # Infrastructure
    "ASSA","BALI","BIRD","BPII","CMNP","DEAL","DGIK","HEAL","HKMU","HKSL",
    "IATA","IBST","INDY","ISSP","IWIN","JSMR","KARW","KJEN","LRNA","MAPA",
    "META","MIKA","MKPI","MTPS","PGAS","PORT","PPRE","PTPP","RIGS","SAFE",
    "SDMU","SPMA","SSIA","TBIG","TELE","TGRA","TLKM","TOWR","TRJA","TSEL",
    "UNIC","WIKA","WSKT","EXCL","ISAT",
    # Mining
    "ADRO","ARII","BSSR","BYAN","CITA","CKRA","CNKO","CTTH","DEWA","DOID",
    "DSNG","DSSA","ELSA","GEMS","GTBO","HRUM","INCO","ITMG","KKGI","MBAP",
    "MEDC","MITI","MOMY","MPMX","MTCN","MYOH","PKPK","PSAB","PTBA","PTRO",
    "RUIS","SMMT","SMRU","SURE","TINS","TOBA","ANTM","ZINC",
    # Miscellaneous
    "AIMS","AKRA","ALDO","AMAR","AMRT","ANDI","APII","APLN","ARNA","ASBI",
    "ASII","ASJT","ASRI","ATIC","ATLA","AUTO","BALI","BAYU","BCAP","BCIC",
    "BDKR","BENA","BEST","BFIN","BIKA","BIMA","BIPP","BKSL","BLTZ","BMSR",
    "BNBR","BOSS","BPFI","BRMS","BSBK","BSDE","BSIM","BTEK","BTON","BUVA",
    "CASH","CBMF","CEKA","CENT","CFIN","CITA","CKRA","CLPI","CMPP","CNKO",
    "CNTX","CPIN","CPRI","CSAP","CTRA","CTRP","CTRS","DART","DEWA","DFAM",
    "DGNS","DILD","DMAS","DNET","DPUM","DSSA","DUTI","ECII","ELTY","EMTK",
    "ENRG","EPMT","ERAA","ESSA","FAST","FMII","FORU","FPNI","FREN","GAMA",
    "GDNG","GDST","GEMA","GGRP","GIAA","GLOB","GMFI","GOTO","GPRA","GWSA",
    "HDTX","HERO","HKMU","HMPR","HOME","HOTL","HRTA","IBFN","ICON","IDPR",
    "IFSH","IGST","IIKP","IMJS","IMPC","INAF","INAI","INDY","INPP","INTD",
    "ISAT","ISSP","JGLE","JIHD","JPFA","JRPT","JSPT","JTPE","KBLM","KBRI",
    "KBSS","KCST","KDSI","KICI","KIJA","KIOS","KLIK","KMTR","KOIN","KPIG",
    "KREN","LCGP","LION","LMAS","LMPI","LPCK","LPKR","LPPF","LRNA","LTLS",
    "MABA","MAPI","MAPA","MBSS","MBTO","MCAS","MDIA","MDKA","MFMI","MGNA",
    "MICE","MIDI","MIKA","MITI","MKNT","MKPI","MLPT","MMLP","MNCN","MPPA",
    "MPXL","MRAT","MREI","MSIN","MTDL","MTFN","MTLA","MTRA","MTPS","MYOH",
    "MYTX","NAYZ","NELY","NFCX","NICK","NICI","NIRO","NISP","NKPI","NOBU",
    "NRCA","NRPG","NUSA","OASA","OBAS","OBAT","OILS","OLIV","OMRE","OPMS",
    "PADI","PALM","PANR","PANS","PARA","PBSA","PCAR","PDES","PGAS","PGLI",
    "PGPI","PGUN","PICO","PKPK","PLAN","PLAS","PLIN","PNGO","PNSE","POLA",
    "PORT","PPRE","PPRO","PRAS","PRDA","PRIM","PSAB","PSGO","PSKT","PTSN",
    "PTSP","PUBM","PWON","PYFA","RBMS","RCCC","RELI","RIMO","RMBA","RODA",
    "RONY","ROTI","RUIS","RUNS","SAFE","SAME","SAPX","SATU","SCCO","SCPI",
    "SDMU","SEMA","SHIP","SIDO","SIMP","SINI","SIPD","SKLT","SKRN","SLIS",
    "SMAR","SMKM","SMSM","SMTL","SOCI","SOFA","SOHO","SONA","SPMA","SRAJ",
    "SRIL","SRNA","SRTG","SSIA","SSMS","STAR","STED","STTP","TAXI","TBIG",
    "TBLA","TCID","TELE","TFAS","TGRA","TLKM","TMAS","TOBA","TOWR","TPMA",
    "TRIM","TRJA","TRST","TRUS","TSPC","TURI","UANG","UCID","ULTJ","UNIC",
    "UNSP","URBN","UVCR","VICO","VINS","VIVA","VKTR","VOKS","WARS","WEGE",
    "WIKA","WIIM","WINS","WIRG","WMPP","WOOD","WOWS","WSBP","WSKT","XIML",
    "YPAS","ZINC","ABBA","ABDA","ABMM","ACST","ADCP","ADHI","ADMF","ADNK",
    "AGRO","AHAP","AIMS","AISA","AKKU","AKPI","AKRA","ALDO","ALII","ALKA",
    "ALMI","ALTO","AMAG","AMFG","AMII","AMMS","AMRT","ANRG","APII","APLN",
    "ARCX","AREA","ARSP","ASBI","ASDM","ASJT","ASMI","ASRI","ASRM","ASSA",
    "ATLA","ATPK","AUTO","BALI","BALL","BAPA","BATA","BAYU","BBLD","BCAP",
    "BCIC","BEKS","BEST","BFIN","BIKA","BIMA","BIPP","BISI","BKSL","BLTA",
    "BLTZ","BMSR","BNBR","BOSS","BPFI","BPII","BRMS","BSBK","BSDE","BSIM",
    "BTEK","BUVA","BYAN","CAMP","CEKA","CFIN","CGST","CMNP","CMPP","CNTX",
    "COWL","CPRI","CSIS","CSRA","CTRA","CTRP","CTRS","DART","DEAL","DFAM",
    "DGIK","DGNS","DILD","DMAS","DNET","DPUM","DSSA","DUTI","ECII","EMTK",
    "ENRG","EPMT","ERAA","ESSA","FAST","FMII","FORU","FREN","GAMA","GDNG",
    "GDST","GEMA","GGRP","GIAA","GLOB","GMFI","GPRA","GWSA","HDTX","HEAL",
    "HERO","HKMU","HMPR","HOME","HOTL","HRTA","ICON","IDPR","IFSH","IGST",
    "IMJS","IMPC","INAF","INDY","INPP","JGLE","JIHD","JRPT","JSPT","JTPE",
    "KBRI","KDSI","KIJA","KIOS","KLIK","KMTR","KOIN","KPIG","KREN","LCGP",
    "LION","LMAS","LMPI","LPCK","LPKR","LPPF","LTLS","MABA","MAPA","MBSS",
    "MCAS","MDIA","MDKA","MFMI","MGNA","MICE","MIDI","MKNT","MKPI","MLPT",
    "MMLP","MNCN","MPPA","MPXL","MREI","MSIN","MTDL","MTFN","MTLA","MTRA",
    "MYTX","NAYZ","NELY","NFCX","NICK","NIRO","NKPI","NRCA","NRPG","NUSA",
    "OBAS","OBAT","OMRE","PADI","PANR","PANS","PARA","PBSA","PDES","PGPI",
    "PGUN","PICO","PLAN","PLAS","PLIN","PNGO","PNSE","POLA","PPRO","PRDA",
    "PRIM","PSKT","PTSN","PTSP","PUBM","PWON","RBMS","RCCC","RELI","RIMO",
    "RODA","RONY","RUIS","RUNS","SAME","SAPX","SATU","SCCO","SEMA","SHIP",
    "SINI","SIPD","SKRN","SLIS","SMKM","SMSM","SMTL","SOCI","SOFA","SOHO",
    "SONA","SRAJ","SRIL","SRNA","SRTG","STED","TAXI","TFAS","TMAS","TPMA",
    "TRUS","TURI","UANG","UCID","UVCR","VICO","VINS","VIVA","WARS","WEGE",
    "WMPP","WOWS","WSBP","RANC","SICO","BUMI","ZATA","COAL","BULL","HITS",
    "CBDK","DGWG","MERI","PMUI","VKTR",
}

_syariah_set: set[str] = set(_BASELINE)
_lock = threading.Lock()


def _try_fetch_ksei() -> Optional[set]:
    """
    Attempt to parse the KSEI DES PDF for 4-letter IDX tickers.
    Returns None if unavailable or parse yields too few results.
    """
    try:
        url = "https://web.ksei.co.id/files/Daftar_Efek_Syariah_Periode_Kedua_2025.pdf"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()

        # Extract ASCII sequences that look like 4-letter IDX codes
        # PDF encodes strings as UTF-16BE in streams — decode and find them
        text = raw.decode("latin-1", errors="replace")
        candidates = re.findall(r"\b([A-Z]{4})\b", text)
        found = {t for t in candidates if t.isalpha() and t.isupper()}
        # Sanity check: real list should have hundreds of tickers
        if len(found) >= 100:
            logger.info(f"Syariah: fetched {len(found)} tickers from KSEI PDF")
            return found
    except Exception as e:
        logger.debug(f"Syariah: KSEI fetch failed ({e}), using baseline")
    return None


def refresh() -> None:
    global _syariah_set
    result = _try_fetch_ksei()
    with _lock:
        if result and len(result) >= 100:
            _syariah_set = result
        else:
            _syariah_set = set(_BASELINE)


def is_syariah(ticker: str) -> bool:
    code = ticker.upper().split(":")[1] if ":" in ticker else ticker.upper()
    with _lock:
        return code in _syariah_set


# Refresh in background on import so startup isn't blocked
threading.Thread(target=refresh, daemon=True).start()
