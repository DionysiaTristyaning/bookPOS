(function () {
  const TOKEN_KEYS = ["token", "bookpos_token", "jwt"];
  let tarifPajak = 0;

  function getToken() {
    for (const k of TOKEN_KEYS) {
      const v = localStorage.getItem(k);
      if (v) return v;
    }
    return "";
  }

  function authHeaders() {
    const h = { "Content-Type": "application/json" };
    const t = getToken();
    if (t) h["Authorization"] = "Bearer " + t;
    return h;
  }

  function rupiah(angka) {
    return "Rp " + Math.round(Number(angka) || 0).toLocaleString("id-ID");
  }

  async function loadConfig() {
    try {
      const res = await fetch("/api/config");
      const data = await res.json();
      tarifPajak = Number(data.tarif_pajak) || 0;
    } catch (e) {
      tarifPajak = 0;
    }
    return tarifPajak;
  }

  function hitungTotal(items) {
    const subtotal = items.reduce((s, it) => s + it.harga_jual * it.qty, 0);
    const pajak = Math.round(subtotal * tarifPajak);
    return { subtotal, pajak, total: subtotal + pajak };
  }

  function hitungKembalian(total, tunai) {
    return Math.max(0, Number(tunai) - total);
  }

  async function checkout(items, metode, tunaiDiterima) {
    const res = await fetch("/api/checkout", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({
        items: items.map((it) => ({ id: it.id, qty: it.qty })),
        metode_pembayaran: metode,
        tunai_diterima: tunaiDiterima,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Checkout gagal");
    return data.transaction;
  }

  window.POS = {
    getToken,
    authHeaders,
    rupiah,
    loadConfig,
    hitungTotal,
    hitungKembalian,
    checkout,
  };
})();