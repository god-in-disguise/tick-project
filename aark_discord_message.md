# Aark Integration Message

Hey Aark team, we are building TICK: a mobile-first volatility discovery and trading app. Users move through the markets with the most interesting price action and can open or close a high-leverage position in seconds through a simple mobile interface.

We completed a live integration test with Aark. Depositing USDC, delegated execution, opening a BTC 500x position, closing it, reconciling the result, and withdrawing all worked.

The remaining issue is seamless order authorization. A trade opened successfully with a valid `TRADE` reCAPTCHA token from `app.aark.digital`, but TICK needs to generate authorization from our own PWA without sending users to the Aark interface.

Could you provide partner/integrator authentication, or authorize our staging and production domains for the required reCAPTCHA flow? Who is the best person on the team to discuss the B2B integration with?
