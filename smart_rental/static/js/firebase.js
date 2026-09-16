const firebaseConfig = {
  apiKey: "AIzaSyAkv604AR4Xaou0WHETZnW3-xyb4dZNXHw",
  authDomain: "datn-smartrental.firebaseapp.com",
  databaseURL: "https://datn-smartrental-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "datn-smartrental",
  storageBucket: "datn-smartrental.firebasestorage.app",
  messagingSenderId: "877783697255",
  appId: "1:877783697255:web:7b6b1e369681221f5711c2"
};

if (!firebase.apps.length) {
  firebase.initializeApp(firebaseConfig);
}

const firebaseAuth = firebase.auth();