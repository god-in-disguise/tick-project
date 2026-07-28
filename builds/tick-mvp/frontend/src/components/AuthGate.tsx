import { KeyRound } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { Session } from "../types";

type Props = {
  onAuthenticated: (session: Session) => void;
};

type GoogleCredentialResponse = { credential: string };

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (options: {
            client_id: string;
            callback: (response: GoogleCredentialResponse) => void;
          }) => void;
          renderButton: (
            element: HTMLElement,
            options: Record<string, string | number | boolean>
          ) => void;
        };
      };
    };
  }
}

export function AuthGate({ onAuthenticated }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const googleButton = useRef<HTMLDivElement>(null);
  const clientId = String(import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "");
  const demoEnabled = import.meta.env.VITE_DEMO_AUTH_ENABLED === "true";

  useEffect(() => {
    if (!import.meta.env.DEV || import.meta.env.VITE_AUTO_DEV_AUTH === "false") return;
    setBusy(true);
    api.devSession(String(import.meta.env.VITE_DEV_USER_ID ?? "funded-dev"))
      .then(onAuthenticated)
      .catch((cause) => setError(message(cause)))
      .finally(() => setBusy(false));
  }, [onAuthenticated]);

  useEffect(() => {
    if (!clientId || !googleButton.current) return;
    const render = () => {
      if (!window.google || !googleButton.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => {
          setBusy(true);
          api.googleSession(response.credential)
            .then(onAuthenticated)
            .catch((cause) => setError(message(cause)))
            .finally(() => setBusy(false));
        }
      });
      window.google.accounts.id.renderButton(googleButton.current, {
        type: "standard",
        theme: "filled_black",
        size: "large",
        shape: "rectangular",
        text: "continue_with",
        width: 310
      });
    };
    if (window.google) {
      render();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = render;
    document.head.appendChild(script);
    return () => script.remove();
  }, [clientId, onAuthenticated]);

  const submitDemo = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onAuthenticated(await api.demoSession(email, name, accessCode));
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
        <span>YOUR TRADING WALLET</span>
        <h1>Enter the live tape.</h1>
        <p>Your TICK wallet is created automatically and linked to this account.</p>
        {clientId ? <div className="google-button" ref={googleButton} /> : null}
        {demoEnabled ? (
          <form className="demo-auth" onSubmit={submitDemo}>
            <input
              type="email"
              autoComplete="email"
              placeholder="Email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <input
              type="text"
              autoComplete="name"
              placeholder="Name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <input
              type="password"
              autoComplete="one-time-code"
              placeholder="Demo access code"
              value={accessCode}
              onChange={(event) => setAccessCode(event.target.value)}
              required
            />
            <button type="submit" disabled={busy}>
              <KeyRound size={17} />
              {busy ? "Opening TICK" : "Enter private demo"}
            </button>
          </form>
        ) : null}
        {!clientId && !demoEnabled && !busy ? (
          <span className="auth-unavailable">Access is not configured on this build.</span>
        ) : null}
        {busy && import.meta.env.DEV ? <span className="auth-unavailable">Opening local session</span> : null}
        {error ? <span className="auth-error">{error}</span> : null}
      </div>
    </main>
  );
}

function message(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}
