async function sendCommand() {
    const cmd = document.getElementById("commandInput").value;
    const res = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd })
    });
    const data = await res.json();
    document.getElementById("output").innerText = data.message;
    document.getElementById("commandInput").value = "";
}

async function getLatest() {
    const res = await fetch("/api/latest");
    const data = await res.json();
    document.getElementById("output").innerText =
        data.command ? `Latest command: ${data.command}` : "No command yet";
}
