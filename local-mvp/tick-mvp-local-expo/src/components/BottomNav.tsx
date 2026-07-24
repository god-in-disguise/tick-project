import React from "react";
import { Pressable, Text, View } from "react-native";

import type { Tab } from "../types";
import { styles } from "../styles";

export function BottomNav({ tab, onTab }: { tab: Tab; onTab: (tab: Tab) => void }) {
  return (
    <View style={styles.navShell}>
      <NavItem label="tick" active={tab === "dashboard"} onPress={() => onTab("dashboard")} />
      <NavItem label="Trade" active={tab === "trade"} primary onPress={() => onTab("trade")} />
      <NavItem label="Me" active={tab === "profile"} onPress={() => onTab("profile")} />
    </View>
  );
}

function NavItem({ label, active, primary, onPress }: { label: string; active: boolean; primary?: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.navItem, primary && styles.navPrimary, active && (primary ? styles.navPrimaryActive : styles.navItemActive)]}>
      <Text style={[styles.navLabel, primary && styles.navPrimaryLabel, active && styles.navLabelActive]}>{label}</Text>
    </Pressable>
  );
}
