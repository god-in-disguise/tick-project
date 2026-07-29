import { ArrowDown, ArrowUp, Plus, Share, Smartphone } from "lucide-react";
import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

import { LandingTape } from "./LandingTape";
import { TickWordmark } from "./TickWordmark";

type InstallPrompt = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

export function InstallLanding() {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  const [instructions, setInstructions] = useState(false);
  const desktop = useDesktopBrowser();

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
      <div className="landing-hero">
        <section className="landing-copy">
          <span>THE MARKET MOVING NOW</span>
          <h1>Catch what is moving now.</h1>
          <p>
            TICK turns live volatility into one focused mobile loop: discover an active
            market, understand the terms, and open or close in one gesture.
          </p>
          <a className="landing-learn-more" href="#how-tick-works">
            Explore TICK
            <ArrowDown size={14} />
          </a>
        </section>
        <InstallAction desktop={desktop} install={install} />
      </div>
      <LandingTape />

      <section
        id="how-tick-works"
        className="landing-product"
        aria-labelledby="landing-product-title"
      >
        <div className="landing-section-heading">
          <span>THE TICK LOOP</span>
          <h2 id="landing-product-title">From movement to a position in seconds.</h2>
          <p>TICK surfaces activity, not direction. The user still decides long or short.</p>
        </div>
        <div className="landing-product-steps">
          <article>
            <span>01 · PULSE</span>
            <h3>Find active markets</h3>
            <p>
              Markets are ranked by live movement, execution cost, freshness, and route
              quality, not by a static watchlist.
            </p>
          </article>
          <article>
            <span>02 · TICK</span>
            <h3>Act with one gesture</h3>
            <p>
              One chart and one visible preset. Swipe up to go long, down to go short,
              and close without building an order ticket.
            </p>
          </article>
          <article>
            <span>03 · RESULT</span>
            <h3>See the real outcome</h3>
            <p>
              Estimated PnL starts after costs. Opening, live exposure, closing, and the
              final wallet result remain separate and explicit.
            </p>
          </article>
        </div>
      </section>

      <section className="landing-principle" aria-labelledby="landing-principle-title">
        <div>
          <span>BUILT FOR REAL EXECUTION</span>
          <h2 id="landing-principle-title">
            Simpler trading without hiding the machinery.
          </h2>
        </div>
        <div className="landing-principle-copy">
          <p>
            TICK normalizes venue differences into the terms that matter on a phone:
            available markets, leverage, estimated cost, opening and closing time, and
            the realized result.
          </p>
          <div className="landing-facts" aria-label="Product capabilities">
            <span>LIVE MARKET DATA</span>
            <span>REAL POSITIONS</span>
            <span>NET RESULTS</span>
            <span>MULTI-VENUE CORE</span>
          </div>
        </div>
      </section>

      <footer className="landing-beta">
        <div>
          <span>PRIVATE BETA · IPHONE FIRST</span>
          <strong>Live markets. Real execution. Invite-only access.</strong>
        </div>
        <TickWordmark className="landing-footer-mark" />
      </footer>

      {instructions && !desktop ? (
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

function InstallAction({
  desktop,
  install
}: {
  desktop: boolean;
  install: () => Promise<void>;
}) {
  return (
    <div className="landing-footer">
      {desktop ? (
        <div className="desktop-handoff">
          <div className="desktop-handoff-qr">
            <QRCodeSVG
              value={installUrl()}
              size={92}
              bgColor="#f3f3ef"
              fgColor="#080b0c"
              level="M"
            />
          </div>
          <div>
            <span>CONTINUE ON IPHONE</span>
            <strong>Scan to open TICK</strong>
            <small>Use your Camera, then add TICK from Safari to your Home Screen.</small>
          </div>
        </div>
      ) : (
        <>
          <button type="button" onClick={() => void install()}>
            <Smartphone size={19} />
            Add TICK to iPhone
          </button>
          <small>The trading app opens from your Home Screen.</small>
        </>
      )}
    </div>
  );
}

function useDesktopBrowser(): boolean {
  const query = "(min-width: 700px) and (hover: hover) and (pointer: fine)";
  const [desktop, setDesktop] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setDesktop(media.matches);
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);

  return desktop;
}

function installUrl(): string {
  const url = new URL(window.location.href);
  url.search = "";
  url.hash = "";
  return url.toString();
}
