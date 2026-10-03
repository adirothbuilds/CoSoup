import { ReactNode } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { colors } from "@stock-scanner/design";
import { ApiError } from "@stock-scanner/client";
export const styles = StyleSheet.create({
  page: { padding: 16, gap: 16 },
  panel: {
    backgroundColor: colors.panel,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 14,
    padding: 16,
    gap: 12,
  },
  title: { fontSize: 25, fontWeight: "600", color: colors.text },
  heading: { fontSize: 18, fontWeight: "600", color: colors.text },
  text: { color: colors.text, fontSize: 14, lineHeight: 21 },
  muted: { color: colors.muted, fontSize: 12, lineHeight: 19 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  input: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 9,
    color: colors.text,
    padding: 12,
    minHeight: 44,
    fontSize: 14,
  },
  button: {
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 9,
    padding: 12,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.raised,
  },
  label: { color: colors.muted, fontSize: 12, marginBottom: 6 },
  badge: { color: colors.accent, fontSize: 11 },
  error: {
    backgroundColor: "#2a1f27",
    borderColor: "#754f52",
    borderWidth: 1,
    padding: 12,
    borderRadius: 9,
    gap: 6,
  },
  code: {
    fontFamily: "Courier",
    fontSize: 10,
    color: colors.muted,
    lineHeight: 16,
  },
  positive: { color: colors.positive },
  negative: { color: colors.negative },
});
export function Panel({
  title,
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  return (
    <View style={styles.panel}>
      {title && <Text style={styles.heading}>{title}</Text>}
      {children}
    </View>
  );
}
export function Button({
  title,
  onPress,
  disabled = false,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      onPress={onPress}
      disabled={disabled}
      style={[styles.button, disabled && { opacity: 0.45 }]}
    >
      <Text style={styles.text}>{title}</Text>
    </Pressable>
  );
}
export function Field({
  label,
  value,
  onChange,
  secret = false,
  multiline = false,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  secret?: boolean;
  multiline?: boolean;
  placeholder?: string;
}) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChange}
        secureTextEntry={secret}
        multiline={multiline}
        autoCapitalize="none"
        autoCorrect={false}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        style={[
          styles.input,
          multiline && { minHeight: 100, textAlignVertical: "top" },
        ]}
      />
    </View>
  );
}
export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <View accessibilityRole="alert" style={styles.error}>
      <Text style={[styles.text, styles.negative]}>
        {error instanceof ApiError ? `${error.code}: ` : ""}
        {error instanceof Error ? error.message : String(error)}
      </Text>
    </View>
  );
}
export function Json({ value }: { value: unknown }) {
  return (
    <Text selectable style={styles.code}>
      {JSON.stringify(value, null, 2)}
    </Text>
  );
}
export function Toggle<T extends string>({
  values,
  value,
  onChange,
}: {
  values: readonly T[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <View
      style={[styles.row, { justifyContent: "flex-start", flexWrap: "wrap" }]}
    >
      {values.map((v) => (
        <Pressable
          key={v}
          accessibilityRole="button"
          accessibilityState={{ selected: value === v }}
          onPress={() => onChange(v)}
          style={[
            styles.button,
            value === v && {
              borderColor: colors.accent,
              backgroundColor: "#28445f",
            },
          ]}
        >
          <Text style={styles.text}>{v}</Text>
        </Pressable>
      ))}
    </View>
  );
}
export function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <View style={{ flex: 1, minWidth: 120, gap: 6, padding: 8 }}>
      <Text style={styles.muted}>{label}</Text>
      <Text style={[styles.heading, { fontSize: 23 }]}>{value}</Text>
      {note && <Text style={styles.muted}>{note}</Text>}
    </View>
  );
}
