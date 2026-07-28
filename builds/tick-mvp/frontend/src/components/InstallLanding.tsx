import { ArrowUp, Plus, Share, Smartphone } from "lucide-react";
import { useEffect, useState } from "react";

import { LandingTape } from "./LandingTape";
import { TickWordmark } from "./TickWordmark";

type InstallPrompt = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

export function InstallLanding() {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  const [instructions, setInstructions] = useState(false);

  useEffect(() => {
    const capture = (event: Event) => {
      event.preventDefault();
      setPrompt(event as InstallPrompt);
    };
    window.addEventListener("beforeinstallprompt", capture);
    return () => window.removeEventListener("beforeinstallprompt", capture);
  }, []);

  const install = async () => {
    if (prompt) {
      await prompt.prompt();
      await prompt.userChoice;
      return;
    }
    setInstructions(true);
  };

  return (
    <main className="install-landing">
      <div className="landing-noise" aria-hidden="true" />
      <header className="landing-header">
        <TickWordmark />
        <span>PRIVATE BETA</span>
      </header>
      <section className="landing-copy">
        <span>THE MARKET MOVING NOW</span>
        <h1>Catch what is moving now.</h1>
        <p>Find live movement, see the cost, and trade through one focused iPhone loop.</p>
      </section>
      <LandingTape />
      <footer className="landing-footer">
        <button type="button" onClick={install}>
          <Smartphone size={19} />
          Add TICK to iPhone
        </button>
        <small>The trading app opens from your Home Screen.</small>
      </footer>

      {instructions ? (
        <div className="install-sheet" role="dialog" aria-modal="true" aria-label="Install TICK">
          <button className="sheet-dismiss" type="button" onClick={() => setInstructions(false)}>
            Done
          </button>
          <div className="install-mark"><span className="tick-candle" /></div>
          <h2>Add TICK to Home Screen</h2>
          <ol>
            <li><Share size={18} /><span>Tap <strong>Share</strong> in Safari.</span></li>
            <li><Plus size={18} /><span>Choose <strong>Add to Home Screen</strong>.</span></li>
            <li><ArrowUp size={18} /><span>Open TICK from the new icon.</span></li>
          </ol>
        </div>
      ) : null}
    </main>
  );
}
