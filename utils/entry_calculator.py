"""
utils/entry_calculator.py

Mengambil string entry_zone dari Decision LLM dan menghitung
titik tengah (midpoint) sebagai harga target order.

Format entry_zone yang didukung:
  "94500-95000"    → midpoint: 94750.0
  "94500 - 95000"  → midpoint: 94750.0
  "94500~95000"    → midpoint: 94750.0
  "~94750"         → 94750.0
  "94750"          → 94750.0
  "around 94750"   → 94750.0  (cari angka pertama)
  "teks tidak ada angka" → fallback_price
"""

import re
import logging

logger = logging.getLogger(__name__)


def parse_entry_midpoint(entry_zone: str, fallback_price: float) -> float:
    """
    Parse string entry_zone dari LLM dan kembalikan midpoint sebagai float.

    Args:
        entry_zone    : String dari field entry_zone decision LLM.
        fallback_price: Harga realtime saat ini, digunakan jika parsing gagal.

    Returns:
        Midpoint entry zone sebagai float.
    """
    if not entry_zone or not isinstance(entry_zone, str):
        logger.warning(f"entry_zone tidak valid: '{entry_zone}', menggunakan fallback {fallback_price}")
        return fallback_price

    # Normalisasi: hapus spasi ekstra, tilde, simbol $
    cleaned = entry_zone.replace("$", "").replace(",", "").strip()

    # Cari semua angka (integer atau float) dalam string
    numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)

    if len(numbers) >= 2:
        # Ada dua angka → hitung midpoint
        low = float(numbers[0])
        high = float(numbers[1])

        # Pastikan urutan benar
        low, high = min(low, high), max(low, high)
        midpoint = (low + high) / 2.0

        logger.debug(f"entry_zone '{entry_zone}' → range [{low}, {high}] → midpoint {midpoint}")
        return midpoint

    elif len(numbers) == 1:
        # Hanya satu angka (misal "~94750" atau "94750")
        price = float(numbers[0])
        logger.debug(f"entry_zone '{entry_zone}' → single price {price}")
        return price

    else:
        # Tidak ada angka ditemukan
        logger.warning(f"Tidak bisa parse entry_zone '{entry_zone}', menggunakan fallback {fallback_price}")
        return fallback_price


def parse_price(price_str: str, fallback: float = 0.0) -> float:
    """
    Parse string harga tunggal dari LLM (stop_loss, target) ke float.

    Args:
        price_str: Contoh: "93800", "$93,800", "93800.5"
        fallback : Nilai jika parsing gagal.

    Returns:
        Harga sebagai float.
    """
    if not price_str or not isinstance(price_str, str):
        return fallback

    cleaned = price_str.replace("$", "").replace(",", "").strip()
    numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)

    if numbers:
        return float(numbers[0])

    logger.warning(f"Tidak bisa parse harga '{price_str}', menggunakan fallback {fallback}")
    return fallback
