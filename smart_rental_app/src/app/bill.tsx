import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { apiGet } from "../lib/api";

type Bill={id?:string;period?:string;consumption?:number;electricity_price?:number;electricity_cost?:number;monthly_rent?:number;service_fee?:number;total_cost?:number;status?:string;generated_at?:string;archived?:boolean};
type Payment={id?:string;period?:string;amount?:number;total_cost?:number;payment_method?:string;paid_at?:string;status?:string};

export default function BillScreen(){
 const [bills,setBills]=useState<Bill[]>([]);const [payments,setPayments]=useState<Payment[]>([]);const [loading,setLoading]=useState(true);
 const load=useCallback(async()=>{try{const [b,p]=await Promise.all([apiGet<Bill[]>("/api/tenant/bills"),apiGet<Payment[]>("/api/tenant/payments")]);setBills(b.data||[]);setPayments(p.data||[]);}catch(e){Alert.alert("Không tải được hóa đơn",e instanceof Error?e.message:"Lỗi API.");}finally{setLoading(false);}},[]);
 useFocusEffect(useCallback(()=>{load()},[load]));
 if(loading)return <SafeAreaView style={styles.safe}><ActivityIndicator size="large" color="#2563EB" style={{marginTop:80}}/></SafeAreaView>;
 const current=bills.find(x=>x.status==="unpaid"||x.status==="pending")||bills[0];
 return <SafeAreaView style={styles.safe}><ScrollView contentContainerStyle={styles.content}>
  <View style={styles.header}><Pressable style={styles.back} onPress={()=>router.back()}><Ionicons name="arrow-back" size={23} color="#172B4D"/></Pressable><Text style={styles.title}>Hóa đơn & thanh toán</Text><View style={{width:42}}/></View>
  <View style={styles.info}><Ionicons name="receipt-outline" size={23} color="#2563EB"/><View style={{flex:1}}><Text style={styles.infoTitle}>Dữ liệu của tenant</Text><Text style={styles.small}>Hóa đơn và lịch sử thanh toán được đọc qua API riêng cho tài khoản của bạn.</Text></View></View>
  <Text style={styles.section}>Hóa đơn gần nhất</Text>
  {current?<View style={styles.bill}><View style={styles.head}><View><Text style={styles.small}>KỲ THANH TOÁN</Text><Text style={styles.period}>{current.period||"--"}</Text></View><Text style={styles.status}>{current.status||"unknown"}</Text></View><Row label="Tiền thuê" value={money(current.monthly_rent)}/><Row label={`Điện (${Number(current.consumption||0).toFixed(2)} kWh)`} value={money(current.electricity_cost)}/><Row label="Phí dịch vụ" value={money(current.service_fee)}/><View style={styles.total}><Text style={styles.totalLabel}>Tổng cộng</Text><Text style={styles.totalValue}>{money(current.total_cost)}</Text></View></View>:<Empty text="Chưa có hóa đơn."/>}
  <Text style={styles.section}>Lịch sử hóa đơn</Text>
  {bills.length?bills.map((b,i)=><View style={styles.item} key={`${b.id||b.period}-${i}`}><View style={{flex:1}}><Text style={styles.period}>{b.period||"--"}</Text><Text style={styles.small}>{b.status||"--"} • {Number(b.consumption||0).toFixed(2)} kWh</Text></View><Text style={styles.money}>{money(b.total_cost)}</Text></View>):<Empty text="Chưa có lịch sử hóa đơn."/>}
  <Text style={styles.section}>Lịch sử thanh toán</Text>
  {payments.length?payments.map((p,i)=><View style={styles.item} key={`${p.id}-${i}`}><View style={{flex:1}}><Text style={styles.period}>{p.period||"--"}</Text><Text style={styles.small}>{p.payment_method||"--"} • {formatDate(p.paid_at)}</Text></View><Text style={styles.money}>{money(p.amount??p.total_cost)}</Text></View>):<Empty text="Chưa có thanh toán."/>}
 </ScrollView></SafeAreaView>;
}
function Row({label,value}:{label:string;value:string}){return <View style={styles.row}><Text style={styles.rowLabel}>{label}</Text><Text style={styles.rowValue}>{value}</Text></View>}
function Empty({text}:{text:string}){return <View style={styles.empty}><Text style={styles.emptyText}>{text}</Text></View>}
function money(n?:number){return Number(n||0).toLocaleString("vi-VN")+" đ"}
function formatDate(v?:string){if(!v)return"--";const d=new Date(v);return Number.isNaN(d.getTime())?v:d.toLocaleDateString("vi-VN")}
const styles=StyleSheet.create({safe:{flex:1,backgroundColor:"#F5F7FB"},content:{padding:20,paddingBottom:40},header:{height:55,flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginBottom:14},back:{width:42,height:42,borderRadius:13,backgroundColor:"#FFF",alignItems:"center",justifyContent:"center",borderWidth:1,borderColor:"#E2E8F0"},title:{fontSize:19,fontWeight:"800",color:"#172B4D"},info:{padding:15,borderRadius:16,backgroundColor:"#EFF6FF",flexDirection:"row",gap:10,alignItems:"center"},infoTitle:{fontSize:13,fontWeight:"800",color:"#172B4D"},small:{fontSize:10,color:"#64748B",marginTop:3},section:{fontSize:18,fontWeight:"800",color:"#172B4D",marginTop:22,marginBottom:10},bill:{backgroundColor:"#FFF",borderRadius:17,padding:16,borderWidth:1,borderColor:"#E2E8F0"},head:{flexDirection:"row",justifyContent:"space-between",alignItems:"flex-start",paddingBottom:10},period:{fontSize:14,fontWeight:"800",color:"#172B4D"},status:{paddingHorizontal:9,paddingVertical:6,borderRadius:13,backgroundColor:"#FFF7ED",color:"#C2410C",fontSize:10,fontWeight:"800"},row:{paddingVertical:12,flexDirection:"row",justifyContent:"space-between"},rowLabel:{fontSize:13,color:"#64748B"},rowValue:{fontSize:13,fontWeight:"700",color:"#172B4D"},total:{marginTop:5,paddingTop:13,borderTopWidth:1,borderTopColor:"#E2E8F0",flexDirection:"row",justifyContent:"space-between"},totalLabel:{fontSize:15,fontWeight:"800",color:"#172B4D"},totalValue:{fontSize:19,fontWeight:"800",color:"#2563EB"},item:{marginTop:8,padding:14,borderRadius:15,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0",flexDirection:"row",alignItems:"center"},money:{fontSize:13,fontWeight:"800",color:"#172B4D"},empty:{padding:20,borderRadius:16,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E2E8F0"},emptyText:{textAlign:"center",color:"#94A3B8"}
});
