import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { formatMoney } from "../market";
import type { AccountState } from "../types";
import { styles } from "../styles";

type Props = {
  state: AccountState | null;
  marginUsd: number;
  softStopUsd: number;
  leverage: number;
  maxLeverage: number;
  approving: boolean;
  onMargin: (value: number) => void;
  onSoftStop: (value: number) => void;
  onApproveMax: () => void;
  onLeverage: (value: number) => void;
};

export function Profile({
  state,
  marginUsd,
  softStopUsd,
  leverage,
  maxLeverage,
  approving,
  onMargin,
  onSoftStop,
  onApproveMax,
  onLeverage
}: Props) {
  const riskLeverage = softStopUsd > 0 ? (marginUsd * leverage) / softStopUsd : leverage;
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
        <Setting label="Margin" value={formatMoney(marginUsd)} />
        <Setting label="Soft stop" value={formatMoney(softStopUsd)} />
        <Setting label="Risk speed" value={`${Math.round(riskLeverage)}x`} />
        <Setting label="Allowance" value={String(state?.balances.allowance ?? "--")} />
      </View>
      <Pressable
        disabled={approving}
        onPress={onApproveMax}
        style={[styles.profileAction, approving && styles.profileActionDisabled]}
      >
        <Text style={styles.profileActionText}>{approving ? "Approving" : "Max allowance"}</Text>
      </Pressable>

      <Text style={styles.controlLabel}>Margin preset</Text>
      <View style={styles.leverageRow}>
        {[10, 20, 50, 100].map((value) => (
          <Pressable
            key={value}
            onPress={() => onMargin(value)}
            style={[styles.leverageButton, marginUsd === value && styles.leverageButtonActive]}
          >
            <Text style={[styles.leverageButtonText, marginUsd === value && styles.leverageButtonTextActive]}>
              {formatMoney(value)}
            </Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.controlLabel}>Stop rail</Text>
      <View style={styles.leverageRow}>
        {[10, 20, 50].map((value) => (
          <Pressable
            key={value}
            onPress={() => onSoftStop(value)}
            style={[styles.leverageButton, softStopUsd === value && styles.leverageButtonActive]}
          >
            <Text style={[styles.leverageButtonText, softStopUsd === value && styles.leverageButtonTextActive]}>
              {formatMoney(value)}
            </Text>
          </Pressable>
        ))}
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
