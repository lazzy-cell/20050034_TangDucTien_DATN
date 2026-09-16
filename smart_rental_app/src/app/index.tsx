import React, { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { API_BASE_URL } from "../lib/api";
import { signIn, signOut } from "../lib/firebase";
import { setProfile } from "../lib/session";
import { registerAndroidPushToken } from "../lib/notifications";

export default function Index() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail || !password) {
      Alert.alert("Thông báo", "Vui lòng nhập email và mật khẩu.");
      return;
    }

    setLoading(true);
    try {
      const result = await signIn(normalizedEmail, password);
      setProfile(result.profile || null);

      if (result.profile?.role !== "tenant") {
        await signOut();
        Alert.alert(
          "Không đúng loại tài khoản",
          "Ứng dụng Smart Rental này dành cho tài khoản tenant. Vui lòng đăng nhập bằng tài khoản tenant của hệ thống."
        );
        return;
      }

      try {
        await registerAndroidPushToken();
      } catch (pushError) {
        console.warn("[notifications] register token failed", pushError);
      }

      router.replace("/home");
    } catch (error) {
      Alert.alert(
        "Đăng nhập thất bại",
        error instanceof Error ? error.message : "Không thể kết nối máy chủ."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        style={styles.keyboard}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.logo}>
            <Ionicons name="home" size={42} color="#FFFFFF" />
          </View>
          <Text style={styles.title}>Smart Rental</Text>
          <Text style={styles.subtitle}>Nhà trọ thông minh</Text>
          <Text style={styles.welcome}>Đăng nhập để kết nối web server</Text>

          <View style={styles.form}>
            <Text style={styles.label}>Email</Text>
            <View style={styles.inputWrap}>
              <Ionicons name="mail-outline" size={21} color="#64748B" />
              <TextInput
                style={styles.input}
                value={email}
                onChangeText={setEmail}
                placeholder="Nhập email Firebase"
                placeholderTextColor="#94A3B8"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                editable={!loading}
              />
            </View>

            <Text style={[styles.label, { marginTop: 18 }]}>Mật khẩu</Text>
            <View style={styles.inputWrap}>
              <Ionicons name="lock-closed-outline" size={21} color="#64748B" />
              <TextInput
                style={styles.input}
                value={password}
                onChangeText={setPassword}
                placeholder="Nhập mật khẩu"
                placeholderTextColor="#94A3B8"
                secureTextEntry={!showPassword}
                autoCapitalize="none"
                editable={!loading}
                onSubmitEditing={handleLogin}
              />
              <Pressable onPress={() => setShowPassword(v => !v)} disabled={loading}>
                <Ionicons
                  name={showPassword ? "eye-off-outline" : "eye-outline"}
                  size={21}
                  color="#64748B"
                />
              </Pressable>
            </View>

            <Pressable
              style={[styles.button, loading && styles.buttonDisabled]}
              onPress={handleLogin}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <>
                  <Ionicons name="log-in-outline" size={21} color="#FFFFFF" />
                  <Text style={styles.buttonText}>Đăng nhập</Text>
                </>
              )}
            </Pressable>

            <View style={styles.serverCard}>
              <Ionicons name="server-outline" size={18} color="#2563EB" />
              <View style={{ flex: 1 }}>
                <Text style={styles.serverLabel}>API SERVER</Text>
                <Text style={styles.serverValue}>{API_BASE_URL}</Text>
              </View>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#F5F7FB" },
  keyboard: { flex: 1 },
  content: { flexGrow: 1, justifyContent: "center", padding: 24 },
  logo: {
    alignSelf: "center",
    width: 82,
    height: 82,
    borderRadius: 25,
    backgroundColor: "#2563EB",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 18,
  },
  title: { textAlign: "center", fontSize: 30, fontWeight: "800", color: "#172B4D" },
  subtitle: { textAlign: "center", marginTop: 3, color: "#64748B", fontSize: 15 },
  welcome: { textAlign: "center", marginTop: 18, color: "#475569" },
  form: { marginTop: 32 },
  label: { fontSize: 13, fontWeight: "700", color: "#334155", marginBottom: 8 },
  inputWrap: {
    minHeight: 54,
    borderRadius: 14,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E2E8F0",
    paddingHorizontal: 15,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  input: { flex: 1, fontSize: 15, color: "#172B4D", paddingVertical: 14 },
  button: {
    height: 54,
    borderRadius: 14,
    backgroundColor: "#2563EB",
    marginTop: 24,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 9,
  },
  buttonDisabled: { opacity: 0.7 },
  buttonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  serverCard: {
    marginTop: 18,
    padding: 13,
    borderRadius: 14,
    backgroundColor: "#EFF6FF",
    flexDirection: "row",
    gap: 10,
    alignItems: "center",
  },
  serverLabel: { fontSize: 9, fontWeight: "800", color: "#64748B", letterSpacing: 0.8 },
  serverValue: { fontSize: 12, color: "#1E40AF", marginTop: 2 },
});
