import React, { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { apiGet } from "../lib/api";

type History={id?:string;timestamp?:string;consumption?:number;energy?:number;kwh?:number;power?:number};
type Bill={period?:string;consumption?:number;total_cost?:number};

export default function EnergyScreen(){
 const [history,setHistory]=useState<History[]>([]);const [bills,setBills]=useState<Bill[]>([]);const [loading,setLoading]=useState(true);const [days,setDays]=useState(7);
 const load=useCallback(async()=>{try{const [h,b]=await Promise.all([apiGet<History[]>("/api/tenant/energy-history?limit=200"),apiGet<Bill[]>("/api/tenant/bills")]);setHistory(h.data||[]);setBills(b.data||[]);}catch(e){Alert.alert("Không tải được điện năng",e instanceof Error?e.message:"Lỗi API.");}finally{setLoading(false);}},[]);
 useFocusEffect(useCallback(()=>{load()},[load]));
 const recent=useMemo(()=>[...history].sort((a,b)=>String(a.timestamp).localeCompare(String(b.timestamp))).slice(-days),[history,days]);
 const values=recent.map(x=>Number(x.consumption??x.energy??x.kwh??0));const total=values.reduce((a,b)=>a+b,0);const max=Math.max(...values,1);
 if(loading)return <SafeAreaView style={styles.safe}><ActivityIndicator size="large" color="#2563EB" style={{marginTop:80}}/></SafeAreaView>;
 return <SafeAreaView style={styles.safe}><ScrollView contentContainerStyle={styles.content}>
  <View style={styles.header}><Pressable style={styles.back} onPress={()=>router.back()}><Ionicons name="arrow-back" size={23} color="#172B4D"/></Pressable><Text style={styles.title}>Điện năng</Text><View style={{width:42}}/></View>
  <View style={styles.total}><Text style={styles.small}>TIÊU THỤ TRONG {days} BẢN GHI GẦN NHẤT</Text><Text style={styles.totalValue}>{total.toFixed(2)} <Text style={styles.unit}>kWh</Text></Text><Text style={styles.smallLight}>{history.length} bản ghi từ API tenant</Text></View>
  <View style={styles.tabs}><Pressable style={[styles.tab,days===7&&styles.active]} onPress={()=>setDays(7)}><Text style={[styles.tabText,days===7&&styles.activeText]}>7 bản ghi</Text></Pressable><Pressable style={[styles.tab,days===30&&styles.active]} onPress={()=>setDays(30)}><Text style={[styles.tabText,days===30&&styles.activeText]}>30 bản ghi</Text></Pressable></View>
  <Text style={styles.section}>Lịch sử tiêu thụ</Text>
  <View style={styles.chart}>{recent.length?recent.map((x,i)=>{const v=Number(x.consumption??x.energy??x.kwh??0);return <View style={styles.barCol} key={`${x.id||x.timestamp}-${i}`}><View style={styles.barWrap}><View style={[styles.bar,{height:`${Math.max(2,v/max*100)}%`}]} /></View><Text style={styles.barLabel}>{label(x.timestamp)}</Text></View>}):<Text style={styles.empty}>Chưa có dữ liệu.</Text>}</View>
  <Text style={styles.section}>Tóm tắt hóa đơn</Text>
  {bills.length?bills.slice(0,5).map((b,i)=><View style={styles.item} key={`${b.period}-${i}`}><View style={{flex:1}}><Text style={styles.period}>{b.period||"--"}</Text><Text style={styles.small}>{Number(b.consumption||0).toFixed(2)} kWh</Text></View><Text style={styles.money}>{money(b.total_cost)}</Text></View>):<View style={styles.item}><Text style={styles.small}>Chưa có hóa đơn.</Text></View>}
 </ScrollView></SafeAreaView>;
}
function label(v?:string){if(!v)return"--";const d=new Date(v);return Number.isNaN(d.getTime())?"":`${d.getDate()}/${d.getMonth()+1}`}
function money(n?:number){return Number(n||0).toLocaleString("vi-VN")+" đ"}
const styles=StyleSheet.create({safe:{flex:1,backgroundColor:"#F5F7FB"},content:{padding:20,paddingBottom:40},header:{height:55,flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginBottom:14},back:{width:42,height:42,borderRadius:13,backgroundColor:"#FFF",alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:"#E2E8F0"},title:{fontSize:19,fontWeight:"800",color:"#172B4D"},total:{padding:18,borderRadius:18,backgroundColor:"#2563EB"},small:{fontSize:10,color:"#64748B",fontWeight:"700"},smallLight:{fontSize:10,color:"#DBEAFE",marginTop:2},totalValue:{fontSize:30,fontWeight:"800",color:"#FFF",marginVertical:6},unit:{fontSize:12,color:"#DBEAFE"},tabs:{marginTop:15,padding:4,borderRadius:14,backgroundColor:"#E2E8F0",flexDirection:"row"},tab:{flex:1,paddingVertical:10,alignItems:"center",borderRadius:11},active:{backgroundColor:"#FFF"},tabText:{fontSize:12,fontWeight:"700",color:"#64748B"},activeText:{color:"#2563EB"},section:{fontSize:18,fontWeight:"800",color:"#172B4D",marginTop:22,marginBottom:10},chart:{height:220,padding:14,borderRadius:16,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0",flexDirection:"row",alignItems:"flex-end",gap:5},barCol:{flex:1,height:"100%",alignItems:"center"},barWrap:{flex:1,width:"65%",justifyContent:"flex-end"},bar:{width:"100%",backgroundColor:"#2563EB",borderRadius:5,minHeight:2},barLabel:{fontSize:8,color:"#64748B",marginTop:5},empty:{alignSelf:"center",color:"#94A3B8"},item:{marginTop:8,padding:14,borderRadius:15,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0",flexDirection:"row",alignItems:"center"},period:{fontSize:14,fontWeight:"800",color:"#172B4D"},money:{fontSize:13,fontWeight:"800",color:"#172B4D"}
});
