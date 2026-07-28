type Props = {
  className?: string;
};

export function TickWordmark({ className = "" }: Props) {
  return (
    <span className={`tick-wordmark ${className}`.trim()} aria-label="TICK">
      <span aria-hidden="true">T</span>
      <span className="tick-wordmark-candle" aria-hidden="true" />
      <span aria-hidden="true">CK</span>
    </span>
  );
}
