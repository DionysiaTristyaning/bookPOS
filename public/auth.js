const Auth = {
    get token() { return localStorage.getItem("token"); },
    get user() {
        try { return JSON.parse(localStorage.getItem("user")); } catch { return null; }
    },
    save(token, user) {
        localStorage.setItem("token", token);
        localStorage.setItem("user", JSON.stringify(user));
    },
    logout() {
        localStorage.removeItem("token");
        localStorage.removeItem("user");
        location.replace("/login.html");
    },
};

// 1) Belum login? Lempar ke halaman login.
if (!Auth.token) location.replace("/login.html");

// 2) Semua fetch ke /api/ otomatis membawa token; 401 -> login ulang.
const _fetch = window.fetch;
window.fetch = async (url, opts = {}) => {
    const isApi = typeof url === "string" && url.startsWith("/api/");
    if (isApi) {
        opts.headers = { ...(opts.headers || {}), Authorization: "Bearer " + Auth.token };
    }
    const res = await _fetch(url, opts);
    if (isApi && res.status === 401) Auth.logout();
    return res;
};