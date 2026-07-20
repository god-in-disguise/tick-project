import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { formatMoney } from "../market";
import type { AccountState } from "../types";
import { styles } from "../styles";

type Props = {
  state: AccountState | null;
  ticketUsd: number;
  leverage: number;
  maxLeverage: number;
  onLeverage: (value: number) => void;
};

export function Profile({ state, ticketUsd, leverage, maxLeverage, onLeverage }: Props) {
  return (
    <ScrollView style={styles.page} contentContainerStyle={styles.pageContent} showsVerticalScrollIndicator={false}>
      <Text style={styles.pageTitle}>Me</Text>
      <View style={styles.accountHero}>
        <Text style={styles.micro}>TICK balance</Text>
        <Text style={styles.accountBalance}>{formatMoney(state?.balances.usdc ?? 0)}</Text>
        <Text numberOfLines={1} style={styles.walletAddress}>{state?.address ?? "Connecting"}</Text>
      </View>

      <View style={styles.settingsPanel}>
        <Setting label="Venue" value={(state?.venue ?? "ostium").toUpperCase()} />
        <Setting label="Ticket" value={formatMoney(ticketUsd)} />
        <Setting label="Margin" value="Isolated" />
        <Setting label="Allowance" value={String(state?.balances.allowance ?? "--")} />
      </View>

      <Text style={styles.controlLabel}>Leverage preset</Text>
      <View style={styles.leverageRow}>
        {[25, 50, 100, 250, 500].map((value) => {
          const disabled = value > maxLeverage;
          return (
            <Pressable
              key={value}
              disabled={disabled}
              onPress={() => onLeverage(value)}
              style={[styles.leverageButton, leverage === value && styles.leverageButtonActive, disabled && styles.leverageButtonDisabled]}
            >
              <Text style={[styles.leverageButtonText, leverage === value && styles.leverageButtonTextActive]}>{value}x</Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={styles.profileFootnote}>ETH for gas: {(state?.balances.eth ?? 0).toFixed(6)}</Text>
    </ScrollView>
  );
}

function Setting({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.settingRow}>
      <Text style={styles.settingLabel}>{label}</Text>
      <Text style={styles.settingValue}>{value}</Text>
    </View>
  );
}
