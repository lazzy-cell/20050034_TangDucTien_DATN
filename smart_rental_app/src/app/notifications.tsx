import React, { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { apiGet } from "../lib/api";

type Notification={
  id:string;
  title?:string;
  body?:string;
  message?:string;
  type?:string;
  scope?:"global"|"private"|"system"|string;
  read?:boolean;
  created_at?:string;
  data?:Record<string, unknown>;
};

function getScope(x: Notification){
  return String(x.scope || x.data?.scope || (x.data?.target === "all_tenants" ? "global" : "private"));
}

export default function NotificationsScreen(){
 const [items,setItems]=useState<Notification[]>([]);const [loading,setLoading]=useState(true);
 const load=useCallback(async()=>{try{const r=await apiGet<Notification[]>("/api/tenant/notifications?limit=100");setItems(r.data||[]);}catch(e){}finally{setLoading(false)}},[]);
 useFocusEffect(useCallback(()=>{load()},[load]));
 if(loading)return <SafeAreaView style={styles.safe}><ActivityIndicator size="large" color="#2563EB" style={{marginTop:80}}/></SafeAreaView>;
 return <SafeAreaView style={styles.safe}><ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={false} onRefresh={load}/>}> 
  <View style={styles.header}><Pressable style={styles.back} onPress={()=>router.back()}><Ionicons name="arrow-back" size={23} color="#172B4D"/></Pressable><Text style={styles.title}>Thông báo</Text><View style={{width:42}}/></View>
  <View style={styles.info}><Ionicons name="notifications-outline" size={22} color="#2563EB"/><View style={{flex:1}}><Text style={styles.infoTitle}>Lịch sử thông báo</Text><Text style={styles.small}>Bao gồm thông báo toàn người dùng và thông báo riêng dành cho phòng/tài khoản của bạn.</Text></View></View>
  {items.length===0?<View style={styles.empty}><Ionicons name="notifications-off-outline" size={38} color="#94A3B8"/><Text style={styles.emptyTitle}>Không có thông báo</Text></View>:items.map((x,i)=>{
    const scope=getScope(x); const global=scope==="global"; const room=typeof x.data?.room_name === "string" ? String(x.data?.room_name) : "";
    return <View style={styles.item} key={`${x.id}-${i}`}>
      <View style={[styles.icon, global?styles.globalIcon:styles.privateIcon]}><Ionicons name={global?"megaphone-outline":"person-outline"} size={21} color="#2563EB"/></View>
      <View style={{flex:1}}>
        <View style={styles.row}><Text style={styles.itemTitle}>{x.title||"Thông báo Smart Rental"}</Text><View style={[styles.badge,global?styles.globalBadge:styles.privateBadge]}><Text style={styles.badgeText}>{global?"TOÀN NGƯỜI DÙNG":"RIÊNG TƯ"}</Text></View></View>
        <Text style={styles.itemText}>{x.body||x.message||""}</Text>
        {room?<Text style={styles.room}>Phòng: {room}</Text>:null}
        <Text style={styles.time}>{formatDate(x.created_at)}</Text>
      </View>
    </View>;
  })}
 </ScrollView></SafeAreaView>
}
function formatDate(v?:string){if(!v)return"--";const normalized=/^(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)$/.test(v)?`${v}Z`:v;const d=new Date(normalized);return Number.isNaN(d.getTime())?v:d.toLocaleString("vi-VN")}
const styles=StyleSheet.create({safe:{flex:1,backgroundColor:"#F5F7FB"},content:{padding:20,paddingBottom:40},header:{height:55,flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginBottom:14},back:{width:42,height:42,borderRadius:13,backgroundColor:"#FFF",alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:"#E2E8F0"},title:{fontSize:19,fontWeight:"800",color:"#172B4D"},info:{padding:15,borderRadius:16,backgroundColor:"#EFF6FF",flexDirection:"row",gap:10,alignItems:"center"},infoTitle:{fontSize:13,fontWeight:"800",color:"#172B4D"},small:{fontSize:11,color:"#64748B",marginTop:3},item:{marginTop:10,padding:14,borderRadius:16,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0",flexDirection:"row",gap:12},icon:{width:42,height:42,borderRadius:12,alignItems:"center",justifyContent:"center"},globalIcon:{backgroundColor:"#EFF6FF"},privateIcon:{backgroundColor:"#F5F3FF"},row:{flexDirection:"row",alignItems:"center",gap:7},itemTitle:{fontSize:14,fontWeight:"800",color:"#172B4D",flex:1},badge:{paddingHorizontal:7,paddingVertical:3,borderRadius:8},globalBadge:{backgroundColor:"#DBEAFE"},privateBadge:{backgroundColor:"#EDE9FE"},badgeText:{fontSize:8,fontWeight:"800",color:"#1E40AF"},itemText:{fontSize:12,color:"#475569",marginTop:5},room:{fontSize:10,color:"#64748B",marginTop:5,fontWeight:"700"},time:{fontSize:10,color:"#94A3B8",marginTop:6},empty:{marginTop:15,padding:30,borderRadius:16,backgroundColor:"#FFF",alignItems:"center"},emptyTitle:{fontSize:15,fontWeight:"800",color:"#64748B",marginTop:8}
});
