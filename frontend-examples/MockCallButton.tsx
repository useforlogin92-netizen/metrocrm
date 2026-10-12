import React, { useState } from "react";

type MockCallStatus = "idle" | "connecting" | "ringing" | "completed" | "error";

export type MockCallLead = {
  executiveId: string | number;
  clientPhone: string;
  leadName: string;
};

type Props = {
  lead: MockCallLead;
  className?: string;
};

/**
 * Standalone React example for a local development harness.
 * MetroCRM's production UI is FastAPI/Jinja; this component is intentionally
 * provided separately and is not wired into the production template bundle.
 */
export default function MockCallButton({ lead, className = "" }: Props) {
  const [status, setStatus] = useState<MockCallStatus>("idle");
  const [message, setMessage] = useState("");
  const [callSid, setCallSid] = useState("");

  async function startMockCall() {
    if (status === "connecting" || status === "ringing") return;
    setStatus("connecting");
    setMessage("");
    setCallSid("");

    try {
      const response = await fetch("/api/telephony/mock-call", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          executive_id: String(lead.executiveId),
          client_phone: lead.clientPhone,
          lead_name: lead.leadName,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || "Mock telephony is disabled or the request failed.");
      }
      setCallSid(data.call_sid || "");
      setStatus("ringing");
      setMessage("📞 Ringing… (simulation only)");
      window.setTimeout(() => {
        setStatus("completed");
        setMessage("Call Completed · mock only");
      }, 1800);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Unable to start mock call.");
    }
  }

  const busy = status === "connecting" || status === "ringing";
  const statusLabel: Record<MockCallStatus, string> = {
    idle: "Call Now (Mock)",
    connecting: "Connecting…",
    ringing: "📞 Ringing…",
    completed: "Call Again (Mock)",
    error: "Retry Mock Call",
  };

  return (
    <span className={`mock-telephony ${className}`} style={{ display: "inline-flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <button
        type="button"
        onClick={startMockCall}
        disabled={busy}
        aria-label={`Start simulated call to ${lead.leadName}`}
        className="rounded-lg bg-blue-600 px-3 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
      >
        {statusLabel[status]}
      </button>
      {message && (
        <span role="status" aria-live="polite" className={status === "error" ? "text-sm text-red-700" : "text-sm text-slate-700"}>
          {message}{callSid ? ` · ${callSid}` : ""}
        </span>
      )}
    </span>
  );
}
