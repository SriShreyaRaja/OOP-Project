const USE_MOCK = false; // Flip to false on Connect Day
const API_BASE = "http://localhost:8000/api";

async function apiGet(path, mockFile) {
  if (USE_MOCK) {
    const res = await fetch("../mock/" + mockFile);
    return res.json();
  }
  const res = await fetch(API_BASE + path, {
    headers: { "Authorization": "Bearer " + sessionStorage.getItem("token") }
  });
  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}

async function apiSend(method, path, body, mockFile = null) {
  if (USE_MOCK) {
    if (mockFile) {
      const res = await fetch(mockFile);
      return res.json();
    }
    alert(`Mock ${method} → ${path}\nBody: ${JSON.stringify(body || {})}`);
    return { status: "ok" };
  }
  const res = await fetch(API_BASE + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + sessionStorage.getItem("token")
    },
    body: body ? JSON.stringify(body) : null
  });
  if (res.status === 204) return null;
  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}

const apiPost = (path, body, mockFile = null) => apiSend("POST", path, body, mockFile);
const apiPut = (path, body) => apiSend("PUT", path, body);

function formatWhyP1(exp) {
  if (!exp) return "";
  if (typeof exp === "string") return exp;
  return `${exp.result || ""} | Formula: ${exp.formula || ""} = <strong>${exp.score}</strong> (${exp.thresholds || ""})`;
}

function renderActionButtons(containerId, incidentId, actions) {
  const box = document.getElementById(containerId);
  box.innerHTML = "";
  const routes = {
    ACKNOWLEDGE: ["/acknowledge", null],
    START_WORK: ["/start", null],
    REQUEST_INFO: ["/request-info", () => ({ question: prompt("Question for reporter:") })],
    PROVIDE_INFO: ["/info", () => ({ answer: prompt("Answer for technician:") })],
    RESOLVE: ["/resolve", () => ({
      fix: prompt("Fix applied (min 10 chars):"),
      rootCause: prompt("Root cause:"),
      preventiveAction: prompt("Preventive action:")
    })],
    VERIFY: ["/verify", null],
    CLOSE: ["/close", null],
    REOPEN: ["/reopen", () => ({ reason: prompt("Reason to reopen:") })],
    ASSIGN: ["/assign", () => ({ technicianId: prompt("Technician ID (e.g. T201):") })]
  };

  (actions || []).forEach(act => {
    if (!routes[act]) return;
    const btn = document.createElement("button");
    btn.textContent = act.replace("_", " ");
    btn.onclick = async () => {
      try {
        const [endpoint, bodyFn] = routes[act];
        const payload = bodyFn ? bodyFn() : null;
        await apiPost(`/incidents/${incidentId}${endpoint}`, payload);
        location.reload();
      } catch (err) {
        alert(`${err.error || "Error"}: ${err.message || "Action failed"}`);
      }
    };
    box.appendChild(btn);
  });
}