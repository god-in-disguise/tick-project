import { KeyRound } from "lucide-react";
import { FormEvent, useState } from "react";

import { api } from "../api";
import type { Session } from "../types";

type Props = {
  onAuthenticated: (session: Session) => void;
};

export function AuthGate({ onAuthenticated }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [accessCode, setAccessCode] = useState("");

  const submitInvite = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onAuthenticated(await api.inviteSession(accessCode));
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-gate">
      <div className="auth-brand">
        <span className="tick-candle" />
        <strong>TICK</strong>
      </div>
      <div className="auth-body">
        <span>PRIVATE ACCESS</span>
        <h1>Enter the live tape.</h1>
        <p>One invite code restores one account and wallet. You can link an email later.</p>
        <form className="invite-auth" onSubmit={submitInvite}>
          <input
            type="password"
            autoComplete="one-time-code"
            placeholder="Invite code"
            value={accessCode}
            onChange={(event) => setAccessCode(event.target.value)}
            required
          />
          <button type="submit" disabled={busy}>
            <KeyRound size={17} />
            {busy ? "Opening TICK" : "Enter TICK"}
          </button>
        </form>
        {error ? <span className="auth-error">{error}</span> : null}
      </div>
    </main>
  );
}

function message(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}
