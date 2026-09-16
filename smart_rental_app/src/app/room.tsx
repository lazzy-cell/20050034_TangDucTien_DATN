import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { apiGet, apiPost } from "../lib/api";
import { getSelectedRoom, setSelectedRoom } from "../lib/session";

type Payload = { room?: any; contract?: any; realtime?: any };

export default function RoomScreen() {
  const [payload, setPayload] = useState<Payload>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await apiGet<Payload>("/api/tenant/room");
      setPayload(res.data || {});
      if (res.data?.room) setSelectedRoom({ ...res.data.room, id: String(res.data.room.id || res.data.room.room_id) });
    } catch (e) {
      Alert.alert("Không tải được phòng", e instanceof Error ? e.message : "Lỗi API.");
    } finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const toggle = async () => {
    if (busy || typeof payload.realtime?.switch !== "boolean") return;
    setBusy(true);
    try {
      const next = !payload.realtime.switch;
      const res = await apiPost<any>("/api/tenant/room/power", { switch: next, reason: next ? "Tenant bật điện từ app" : "Tenant tắt điện từ app" });
      setPayload(p => ({ ...p, realtime: { ...p.realtime, ...(res.data || {}), switch: next } }));
    } catch (e) {
      Alert.alert("Không thể điều khiển điện", e instanceof Error ? e.message : "Lỗi API.");
    } finally { setBusy(false); }
  };

  if (loading) return <SafeAreaView style={styles.safe}><ActivityIndicator size="large" color="#2563EB" style={{marginTop:80}}/></SafeAreaView>;
  const r = payload.room; const rt = payload.realtime || {}; const c = payload.contract || {};
  const on = rt.switch === true;

  return <SafeAreaView style={styles.safe}><ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={false} onRefresh={load}/>}>
    <View style={styles.header}><Pressable style={styles.back} onPress={()=>router.back()}><Ionicons name="arrow-back" size={23} color="#172B4D"/></Pressable><Text style={styles.title}>Thông tin phòng</Text><View style={{width:42}}/></View>
    <View style={styles.hero}><View style={styles.homeIcon}><Ionicons name="home" size={30} color="#2563EB"/></View><View style={{flex:1}}><Text style={styles.label}>PHÒNG</Text><Text style={styles.room}>{r?.room_name || getSelectedRoom()?.room_name || "--"}</Text><Text style={styles.sub}>ID: {r?.id || "--"}</Text></View><View style={[styles.badge,rt.online===false&&styles.offBadge]}><View style={[styles.dot,rt.online===false&&styles.offDot]}/><Text style={[styles.badgeText,rt.online===false&&styles.offText]}>{rt.online===false?"Offline":"Online"}</Text></View></View>

    <Text style={styles.section}>Nguồn điện</Text>
    <View style={styles.powerCard}><View style={[styles.powerIcon,on?styles.onBg:styles.offBg]}><Ionicons name="flash" size={25} color={on?"#2563EB":"#64748B"}/></View><View style={{flex:1}}><Text style={styles.cardTitle}>Trạng thái</Text><Text style={styles.big}>{on?"Đang bật":rt.switch===false?"Đang tắt":"Chưa xác định"}</Text></View><Pressable style={styles.button} onPress={toggle} disabled={busy||typeof rt.switch!=="boolean"}><Text style={styles.buttonText}>{busy?"...":on?"Tắt":"Bật"}</Text></Pressable></View>

    <Text style={styles.section}>Thông số realtime</Text>
    <View style={styles.card}><Metric label="Điện áp" value={rt.voltage} unit="V" icon="flash-outline"/><Metric label="Dòng điện" value={rt.current} unit="A" icon="git-branch-outline"/><Metric label="Công suất" value={rt.power} unit="W" icon="speedometer-outline"/><Metric label="Cập nhật" value={formatDate(rt.updated_at)} unit="" icon="time-outline" text/></View>

    <Text style={styles.section}>Hợp đồng hiện tại</Text>
    <View style={styles.card}><Row label="Trạng thái" value={c.status || "--"}/><Row label="Bắt đầu" value={c.start_date || "--"}/><Row label="Kết thúc" value={c.end_date || "--"}/><Row label="Tiền thuê/tháng" value={money(c.monthly_rent)}/></View>
  </ScrollView></SafeAreaView>;
}
function Metric({label,value,unit,icon,text}:{label:string;value?:any;unit:string;icon:any;text?:boolean}){return <View style={styles.metric}><Ionicons name={icon} size={20} color="#2563EB"/><Text style={styles.metricLabel}>{label}</Text><Text style={styles.metricValue}>{text?String(value||"--"):(typeof value==="number"?value.toFixed(2):"--")} {unit&&<Text style={styles.unit}>{unit}</Text>}</Text></View>}
function Row({label,value}:{label:string;value:string}){return <View style={styles.row}><Text style={styles.rowLabel}>{label}</Text><Text style={styles.rowValue}>{value}</Text></View>}
function money(n?:number){return Number(n||0).toLocaleString("vi-VN")+" đ"}
function formatDate(v?:string){if(!v)return "--";const normalized=/^(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)$/.test(v)?`${v}Z`:v;const d=new Date(normalized);return Number.isNaN(d.getTime())?v:d.toLocaleString("vi-VN")}
const styles=StyleSheet.create({safe:{flex:1,backgroundColor:"#F5F7FB"},content:{padding:20,paddingBottom:40},header:{height:55,flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginBottom:14},back:{width:42,height:42,borderRadius:13,backgroundColor:"#FFF",alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:"#E2E8F0"},title:{fontSize:19,fontWeight:"800",color:"#172B4D"},hero:{padding:17,borderRadius:18,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0",flexDirection:"row",alignItems:"center",gap:12},homeIcon:{width:55,height:55,borderRadius:16,backgroundColor:"#EFF6FF",alignItems:"center",justifyContent:"center"},label:{fontSize:9,fontWeight:"800",color:"#94A3B8"},room:{fontSize:20,fontWeight:"800",color:"#172B4D",marginTop:3},sub:{fontSize:10,color:"#64748B",marginTop:2},badge:{paddingHorizontal:9,paddingVertical:6,borderRadius:14,backgroundColor:"#F0FDF4",flexDirection:"row",gap:5,alignItems:"center"},offBadge:{backgroundColor:"#F1F5F9"},dot:{width:7,height:7,borderRadius:4,backgroundColor:"#16A34A"},offDot:{backgroundColor:"#64748B"},badgeText:{fontSize:10,fontWeight:"700",color:"#166534"},offText:{color:"#64748B"},section:{fontSize:18,fontWeight:"800",color:"#172B4D",marginTop:23,marginBottom:10},powerCard:{padding:16,borderRadius:17,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0",flexDirection:"row",alignItems:"center",gap:12},powerIcon:{width:48,height:48,borderRadius:14,alignItems:"center",justifyContent:"center"},onBg:{backgroundColor:"#EFF6FF"},offBg:{backgroundColor:"#F1F5F9"},cardTitle:{fontSize:11,color:"#64748B"},big:{fontSize:16,fontWeight:"800",color:"#172B4D",marginTop:3},button:{paddingHorizontal:16,paddingVertical:10,borderRadius:11,backgroundColor:"#2563EB"},buttonText:{color:"#FFF",fontWeight:"800"},card:{backgroundColor:"#FFF",borderRadius:16,borderWidth:1,borderColor:"#E2E8F0",paddingHorizontal:15},metric:{paddingVertical:14,borderBottomWidth:1,borderBottomColor:"#F1F5F9",flexDirection:"row",alignItems:"center",gap:11},metricLabel:{flex:1,fontSize:13,color:"#64748B"},metricValue:{fontSize:14,fontWeight:"800",color:"#172B4D"},unit:{fontSize:10,color:"#64748B"},row:{paddingVertical:13,flexDirection:"row",justifyContent:"space-between",borderBottomWidth:1,borderBottomColor:"#F1F5F9"},rowLabel:{fontSize:13,color:"#64748B"},rowValue:{fontSize:13,fontWeight:"800",color:"#172B4D",maxWidth:"55%",textAlign:"right"}
});
