import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { apiGet, apiPost } from "../lib/api";
import { getProfile, getSelectedRoom, setSelectedRoom } from "../lib/session";

type Realtime = { online?: boolean; switch?: boolean; power?: number; voltage?: number; current?: number; updated_at?: string };
type RoomPayload = { room?: any; contract?: any; realtime?: Realtime };

export default function HomeScreen() {
  const [room, setRoom] = useState<any>(getSelectedRoom());
  const [realtime, setRealtime] = useState<Realtime>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (pull = false) => {
    try {
      if (pull) setRefreshing(true);
      const res = await apiGet<RoomPayload>("/api/tenant/room");
      const r = res.data?.room || null;
      setRoom(r);
      setSelectedRoom(r ? { ...r, id: String(r.id || r.room_id) } : null);
      setRealtime(res.data?.realtime || {});
    } catch (e) {
      if (!getSelectedRoom()) {
        setRoom(null);
      }
      Alert.alert("Không tải được dữ liệu", e instanceof Error ? e.message : "Lỗi API.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const togglePower = async () => {
    if (busy || typeof realtime.switch !== "boolean") return;
    setBusy(true);
    try {
      const next = !realtime.switch;
      const res = await apiPost<Realtime>("/api/tenant/room/power", {
        switch: next,
        reason: next ? "Tenant bật điện từ app" : "Tenant tắt điện từ app",
      });
      setRealtime(prev => ({ ...prev, ...(res.data || {}), switch: next }));
    } catch (e) {
      Alert.alert("Không thể điều khiển điện", e instanceof Error ? e.message : "Lỗi API.");
    } finally { setBusy(false); }
  };

  const signOut = async () => {
    const { signOut: firebaseSignOut } = await import("../lib/firebase");
    await firebaseSignOut();
    router.replace("/");
  };

  if (loading) return <SafeAreaView style={styles.safe}><ActivityIndicator size="large" color="#2563EB" style={{ marginTop: 90 }} /></SafeAreaView>;

  const profile = getProfile();
  const switchOn = realtime.switch === true;

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.top}>
          <View>
            <Text style={styles.kicker}>SMART RENTAL</Text>
            <Text style={styles.title}>Xin chào, {String(room?.tenant_name || profile?.name || "bạn")}</Text>
            <Text style={styles.subtitle}>Khu vực quản lý của người thuê</Text>
          </View>
          <Pressable style={styles.logout} onPress={signOut}><Ionicons name="log-out-outline" size={20} color="#475569" /></Pressable>
        </View>

        {room ? <>
          <View style={styles.roomCard}>
            <View style={styles.roomIcon}><Ionicons name="home" size={28} color="#2563EB" /></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>PHÒNG CỦA BẠN</Text>
              <Text style={styles.roomName}>{room.room_name || room.id}</Text>
              <Text style={styles.sub}>ID: {room.id}</Text>
            </View>
            <View style={styles.online}>
              <View style={styles.dot} />
              <Text style={styles.onlineText}>{realtime.online === false ? "Offline" : "Online"}</Text>
            </View>
          </View>

          <Text style={styles.section}>Điều khiển điện</Text>
          <View style={styles.powerCard}>
            <View style={[styles.powerIcon, switchOn ? styles.onBg : styles.offBg]}>
              <Ionicons name="flash" size={26} color={switchOn ? "#2563EB" : "#64748B"} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>Nguồn điện</Text>
              <Text style={styles.bigStatus}>{switchOn ? "Đang bật" : realtime.switch === false ? "Đang tắt" : "Chưa có trạng thái"}</Text>
              <Text style={styles.muted}>{realtime.updated_at ? `Cập nhật ${formatDate(realtime.updated_at)}` : "Dữ liệu từ web server"}</Text>
            </View>
            <Pressable style={[styles.switchButton, switchOn && styles.switchButtonOff]} onPress={togglePower} disabled={busy || typeof realtime.switch !== "boolean"}>
              <Text style={styles.switchText}>{busy ? "..." : switchOn ? "Tắt" : "Bật"}</Text>
            </Pressable>
          </View>

          <Text style={styles.section}>Thông số realtime</Text>
          <View style={styles.grid}>
            <Metric icon="flash-outline" label="Điện áp" value={realtime.voltage} unit="V" />
            <Metric icon="git-branch-outline" label="Dòng điện" value={realtime.current} unit="A" />
            <Metric icon="speedometer-outline" label="Công suất" value={realtime.power} unit="W" />
          </View>

          <Text style={styles.section}>Tiện ích</Text>
          <View style={styles.actions}>
            <Action icon="home-outline" label="Thông tin phòng" onPress={() => router.push("/room")} />
            <Action icon="flash-outline" label="Điện năng" onPress={() => router.push("/energy")} />
            <Action icon="receipt-outline" label="Hóa đơn" onPress={() => router.push("/bill")} />
            <Action icon="document-text-outline" label="Hợp đồng" onPress={() => router.push("/contract")} />
            <Action icon="notifications-outline" label="Thông báo" onPress={() => router.push("/notifications")} />
          </View>
        </> : <View style={styles.empty}>
          <Ionicons name="home-outline" size={42} color="#94A3B8" />
          <Text style={styles.emptyTitle}>Chưa có phòng đang thuê</Text>
          <Text style={styles.muted}>Tài khoản tenant chưa có hợp đồng đang hoạt động.</Text>
        </View>}
      </ScrollView>
    </SafeAreaView>
  );
}

function Metric({ icon, label, value, unit }: { icon: any; label: string; value?: number; unit: string }) {
  return <View style={styles.metric}><Ionicons name={icon} size={21} color="#2563EB" /><Text style={styles.metricLabel}>{label}</Text><Text style={styles.metricValue}>{typeof value === "number" ? value.toFixed(2) : "--"} <Text style={styles.unit}>{unit}</Text></Text></View>;
}
function Action({ icon, label, onPress }: { icon: any; label: string; onPress: () => void }) {
  return <Pressable style={styles.action} onPress={onPress}><View style={styles.actionIcon}><Ionicons name={icon} size={21} color="#2563EB" /></View><Text style={styles.actionText}>{label}</Text><Ionicons name="chevron-forward" size={18} color="#94A3B8" /></Pressable>;
}
function formatDate(v?: string) { if (!v) return "--"; const normalized = /^(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)$/.test(v) ? `${v}Z` : v; const d = new Date(normalized); return Number.isNaN(d.getTime()) ? v : d.toLocaleString("vi-VN"); }

const styles = StyleSheet.create({
  safe:{flex:1,backgroundColor:"#F5F7FB"}, content:{padding:20,paddingBottom:40},
  top:{flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginBottom:18}, kicker:{fontSize:10,fontWeight:"800",letterSpacing:1.2,color:"#2563EB"}, title:{fontSize:22,fontWeight:"800",color:"#172B4D",marginTop:4}, subtitle:{fontSize:11,color:"#64748B",marginTop:3}, logout:{width:42,height:42,borderRadius:13,backgroundColor:"#FFF",alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:"#E2E8F0"},
  roomCard:{padding:16,borderRadius:18,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0",flexDirection:"row",alignItems:"center",gap:12}, roomIcon:{width:54,height:54,borderRadius:16,backgroundColor:"#EFF6FF",alignItems:"center",justifyContent:"center"}, label:{fontSize:9,fontWeight:"800",color:"#94A3B8",letterSpacing:.7}, roomName:{fontSize:19,fontWeight:"800",color:"#172B4D",marginTop:3}, sub:{fontSize:10,color:"#64748B",marginTop:2}, online:{paddingHorizontal:9,paddingVertical:6,borderRadius:13,backgroundColor:"#F0FDF4",flexDirection:"row",alignItems:"center",gap:5}, dot:{width:7,height:7,borderRadius:4,backgroundColor:"#16A34A"}, onlineText:{fontSize:10,fontWeight:"800",color:"#166534"},
  section:{fontSize:18,fontWeight:"800",color:"#172B4D",marginTop:23,marginBottom:10}, powerCard:{padding:16,borderRadius:17,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0",flexDirection:"row",alignItems:"center",gap:12}, powerIcon:{width:48,height:48,borderRadius:14,alignItems:"center",justifyContent:"center"}, onBg:{backgroundColor:"#EFF6FF"},offBg:{backgroundColor:"#F1F5F9"}, cardTitle:{fontSize:12,color:"#64748B"}, bigStatus:{fontSize:16,fontWeight:"800",color:"#172B4D",marginTop:2}, muted:{fontSize:10,color:"#94A3B8",marginTop:3}, switchButton:{paddingHorizontal:16,paddingVertical:10,borderRadius:11,backgroundColor:"#2563EB"}, switchButtonOff:{backgroundColor:"#64748B"}, switchText:{color:"#FFF",fontWeight:"800",fontSize:12},
  grid:{gap:10}, metric:{padding:14,borderRadius:15,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0",flexDirection:"row",alignItems:"center",gap:10},metricLabel:{flex:1,fontSize:12,color:"#64748B"},metricValue:{fontSize:15,fontWeight:"800",color:"#172B4D"},unit:{fontSize:10,color:"#64748B"},
  actions:{gap:9},action:{padding:12,borderRadius:15,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0",flexDirection:"row",alignItems:"center",gap:10},actionIcon:{width:40,height:40,borderRadius:12,backgroundColor:"#EFF6FF",alignItems:"center",justifyContent:"center"},actionText:{flex:1,fontSize:13,fontWeight:"700",color:"#172B4D"}, empty:{marginTop:20,padding:28,borderRadius:17,backgroundColor:"#FFF",alignItems:"center",borderWidth:1,borderColor:"#E2E8F0"},emptyTitle:{fontSize:17,fontWeight:"800",color:"#172B4D",marginTop:12,textAlign:"center"}
});
