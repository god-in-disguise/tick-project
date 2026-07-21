import { StyleSheet } from "react-native";

const color = {
  background: "#0b1416",
  panel: "#121e20",
  panelStrong: "#182628",
  line: "rgba(220,235,231,0.12)",
  text: "#f2f8f6",
  muted: "#7f918d",
  green: "#38d39f",
  red: "#ff6070",
  orange: "#ff9f2e"
};

export const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: color.background
  },
  app: {
    flex: 1,
    backgroundColor: color.background
  },
  content: {
    flex: 1,
    minHeight: 0
  },
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: color.background
  },
  loadingBrand: {
    color: color.text,
    fontSize: 40,
    fontWeight: "900"
  },
  loadingText: {
    color: color.muted,
    marginTop: 10,
    fontSize: 13,
    fontWeight: "700"
  },
  tradeScreen: {
    flex: 1,
    minHeight: 0
  },
  tradeHeader: {
    minHeight: 88,
    paddingHorizontal: 15,
    paddingTop: 8,
    paddingBottom: 7,
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.line,
    backgroundColor: "rgba(7,16,17,0.66)"
  },
  brandRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    minWidth: 0,
    flex: 1
  },
  brand: {
    color: color.text,
    fontSize: 29,
    fontWeight: "900",
    lineHeight: 34,
    marginRight: 13
  },
  marketTitle: {
    flex: 1,
    minWidth: 0
  },
  marketTitleLine: {
    flexDirection: "row",
    alignItems: "baseline",
    minWidth: 0
  },
  symbol: {
    color: color.text,
    fontSize: 20,
    lineHeight: 25,
    fontWeight: "900"
  },
  leverage: {
    fontSize: 18,
    lineHeight: 25,
    fontWeight: "900",
    marginLeft: 6
  },
  assetName: {
    color: color.muted,
    fontSize: 13,
    fontWeight: "700",
    marginLeft: 7,
    flexShrink: 1
  },
  priceLine: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 2
  },
  headerPrice: {
    color: color.text,
    fontSize: 15,
    fontWeight: "800"
  },
  headerMove: {
    fontSize: 12,
    fontWeight: "800",
    marginLeft: 7
  },
  balancePill: {
    minWidth: 104,
    borderWidth: 1,
    borderColor: "rgba(56,211,159,0.42)",
    backgroundColor: "rgba(31,110,82,0.18)",
    borderRadius: 18,
    paddingHorizontal: 13,
    paddingVertical: 7,
    marginLeft: 8
  },
  balanceLabel: {
    color: "#79a995",
    fontSize: 10,
    fontWeight: "800"
  },
  balanceValue: {
    color: color.green,
    fontSize: 19,
    lineHeight: 21,
    fontWeight: "900"
  },
  chartWrap: {
    flex: 1,
    minHeight: 0,
    overflow: "hidden"
  },
  chart: {
    ...StyleSheet.absoluteFillObject
  },
  marketBadge: {
    position: "absolute",
    top: 12,
    left: 14,
    paddingHorizontal: 9,
    paddingVertical: 7,
    borderRadius: 7,
    backgroundColor: "rgba(7,16,17,0.66)",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.line
  },
  badgeTopLine: {
    flexDirection: "row",
    alignItems: "center"
  },
  assetClass: {
    fontSize: 9,
    fontWeight: "900"
  },
  testBadge: {
    color: color.orange,
    fontSize: 8,
    fontWeight: "900",
    marginLeft: 7
  },
  staleBadge: {
    color: color.red,
    fontSize: 8,
    fontWeight: "900",
    marginLeft: 7
  },
  marketState: {
    color: color.text,
    fontSize: 14,
    fontWeight: "800",
    marginTop: 2
  },
  marketMetrics: {
    color: color.muted,
    fontSize: 9,
    fontWeight: "700",
    marginTop: 2
  },
  pnlBadge: {
    position: "absolute",
    left: "25%",
    right: "25%",
    top: "38%",
    alignItems: "center",
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: "rgba(7,16,17,0.52)"
  },
  pnlMeta: {
    color: color.muted,
    fontSize: 10,
    fontWeight: "800"
  },
  pnlValue: {
    fontSize: 36,
    lineHeight: 40,
    fontWeight: "900"
  },
  pnlEstimate: {
    color: color.muted,
    fontSize: 9,
    fontWeight: "700"
  },
  pendingValue: {
    color: color.text,
    fontSize: 24,
    fontWeight: "900",
    marginTop: 2
  },
  gestureCue: {
    position: "absolute",
    top: "34%",
    left: 0,
    right: 0,
    alignItems: "center"
  },
  gestureCueText: {
    color: color.text,
    fontSize: 31,
    fontWeight: "900"
  },
  closedCard: {
    position: "absolute",
    top: "25%",
    left: "13%",
    right: "13%",
    alignItems: "center",
    backgroundColor: "rgba(11,22,23,0.94)",
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: 8,
    padding: 14
  },
  closedLabel: {
    color: color.muted,
    fontSize: 10,
    fontWeight: "800"
  },
  closedPnl: {
    fontSize: 28,
    fontWeight: "900",
    marginTop: 2
  },
  closedSettling: {
    color: color.text,
    fontSize: 23
  },
  closedMeta: {
    color: color.muted,
    fontSize: 10,
    fontWeight: "700",
    marginTop: 3
  },
  closedBreakdown: {
    alignSelf: "stretch",
    flexDirection: "row",
    marginTop: 8,
    paddingTop: 7,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.line
  },
  resultMetric: {
    flex: 1,
    minWidth: 0,
    alignItems: "center"
  },
  resultMetricLabel: {
    color: color.muted,
    fontSize: 8,
    fontWeight: "800"
  },
  resultMetricValue: {
    color: color.text,
    fontSize: 10,
    lineHeight: 14,
    fontWeight: "900",
    marginTop: 1
  },
  errorToast: {
    position: "absolute",
    left: 14,
    right: 14,
    top: 92,
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderRadius: 7,
    backgroundColor: "rgba(92,25,34,0.94)",
    borderWidth: 1,
    borderColor: "rgba(255,96,112,0.35)"
  },
  errorText: {
    color: "#ffd5da",
    fontSize: 11,
    lineHeight: 15,
    fontWeight: "700"
  },
  executionDock: {
    position: "absolute",
    left: 12,
    right: 12,
    bottom: 10,
    padding: 8,
    borderRadius: 8,
    backgroundColor: "rgba(12,23,24,0.84)",
    borderWidth: 1,
    borderColor: color.line
  },
  termRow: {
    flexDirection: "row",
    alignItems: "stretch"
  },
  term: {
    flex: 1,
    minWidth: 0,
    paddingHorizontal: 6,
    paddingVertical: 4,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderRightColor: color.line
  },
  termLabel: {
    color: color.muted,
    fontSize: 8,
    fontWeight: "800"
  },
  termValue: {
    color: color.text,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: "800"
  },
  closeButton: {
    height: 48,
    marginTop: 7,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 7,
    backgroundColor: "rgba(239,246,244,0.96)"
  },
  closeButtonDisabled: {
    opacity: 0.48
  },
  closeButtonText: {
    color: "#071112",
    fontSize: 16,
    fontWeight: "900"
  },
  positive: {
    color: color.green
  },
  negative: {
    color: color.red
  },
  page: {
    flex: 1,
    backgroundColor: color.background
  },
  pageContent: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 40
  },
  pageTitle: {
    color: color.text,
    fontSize: 30,
    fontWeight: "900",
    marginBottom: 14
  },
  hotCard: {
    minHeight: 112,
    padding: 15,
    borderRadius: 8,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: color.panel,
    borderWidth: 1,
    borderColor: color.line
  },
  hotRight: {
    alignItems: "flex-end"
  },
  hotSymbol: {
    color: color.text,
    fontSize: 34,
    fontWeight: "900"
  },
  hotMove: {
    fontSize: 22,
    fontWeight: "900"
  },
  micro: {
    color: color.muted,
    fontSize: 9,
    fontWeight: "800"
  },
  secondaryText: {
    color: color.muted,
    fontSize: 11,
    fontWeight: "700"
  },
  statsRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 8
  },
  metricCard: {
    flex: 1,
    padding: 12,
    minHeight: 70,
    borderRadius: 7,
    backgroundColor: color.panel,
    borderWidth: 1,
    borderColor: color.line
  },
  metricValue: {
    color: color.text,
    fontSize: 21,
    fontWeight: "900",
    marginTop: 6
  },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 20,
    marginBottom: 8
  },
  sectionTitle: {
    color: color.text,
    fontSize: 15,
    fontWeight: "900"
  },
  scannerRow: {
    flexDirection: "row",
    alignItems: "center",
    minHeight: 62,
    paddingHorizontal: 10,
    marginBottom: 6,
    borderRadius: 7,
    backgroundColor: color.panel,
    borderWidth: 1,
    borderColor: color.line
  },
  scannerRank: {
    color: color.muted,
    width: 26,
    fontSize: 10,
    fontWeight: "800"
  },
  scannerIdentity: {
    width: 95
  },
  scannerSymbol: {
    color: color.text,
    fontSize: 15,
    fontWeight: "900"
  },
  scannerActivity: {
    flex: 1,
    minWidth: 0
  },
  scannerTrack: {
    height: 4,
    borderRadius: 2,
    backgroundColor: "rgba(255,255,255,0.07)",
    overflow: "hidden"
  },
  scannerFill: {
    height: 4,
    borderRadius: 2
  },
  scannerMeta: {
    color: color.muted,
    fontSize: 8,
    fontWeight: "700",
    marginTop: 5
  },
  historyRow: {
    minHeight: 56,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 6,
    borderRadius: 7,
    backgroundColor: color.panel
  },
  historySymbol: {
    color: color.text,
    fontSize: 15,
    fontWeight: "900"
  },
  historyPnl: {
    fontSize: 15,
    fontWeight: "900"
  },
  emptyPanel: {
    minHeight: 74,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 7,
    backgroundColor: color.panel
  },
  accountHero: {
    padding: 17,
    borderRadius: 8,
    backgroundColor: "rgba(26,79,63,0.32)",
    borderWidth: 1,
    borderColor: "rgba(56,211,159,0.3)"
  },
  accountBalance: {
    color: color.green,
    fontSize: 37,
    fontWeight: "900",
    marginTop: 3
  },
  walletAddress: {
    color: color.muted,
    fontSize: 10,
    marginTop: 7
  },
  settingsPanel: {
    marginTop: 12,
    borderRadius: 8,
    backgroundColor: color.panel,
    paddingHorizontal: 13
  },
  settingRow: {
    minHeight: 48,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.line
  },
  settingLabel: {
    color: color.muted,
    fontSize: 12,
    fontWeight: "700"
  },
  settingValue: {
    color: color.text,
    fontSize: 12,
    fontWeight: "800"
  },
  controlLabel: {
    color: color.text,
    fontSize: 14,
    fontWeight: "900",
    marginTop: 21,
    marginBottom: 9
  },
  leverageRow: {
    flexDirection: "row",
    gap: 8
  },
  leverageButton: {
    flex: 1,
    height: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 7,
    backgroundColor: color.panel,
    borderWidth: 1,
    borderColor: color.line
  },
  leverageButtonActive: {
    borderColor: color.orange,
    backgroundColor: "rgba(255,159,46,0.14)"
  },
  leverageButtonDisabled: {
    opacity: 0.3
  },
  leverageButtonText: {
    color: color.muted,
    fontSize: 14,
    fontWeight: "900"
  },
  leverageButtonTextActive: {
    color: color.orange
  },
  profileFootnote: {
    color: color.muted,
    fontSize: 10,
    marginTop: 15,
    textAlign: "center"
  },
  navShell: {
    height: 72,
    marginHorizontal: 12,
    marginTop: 5,
    marginBottom: 7,
    padding: 5,
    flexDirection: "row",
    alignItems: "center",
    borderRadius: 30,
    backgroundColor: "rgba(17,29,31,0.98)",
    borderWidth: 1,
    borderColor: color.line
  },
  navItem: {
    flex: 1,
    height: 52,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 25
  },
  navItemActive: {
    backgroundColor: "rgba(255,255,255,0.05)"
  },
  navPrimary: {
    flex: 1.35
  },
  navPrimaryActive: {
    backgroundColor: color.text
  },
  navLabel: {
    color: "#667875",
    fontSize: 12,
    fontWeight: "900"
  },
  navPrimaryLabel: {
    color: "#90a19e"
  },
  navLabelActive: {
    color: "#071112"
  }
});
