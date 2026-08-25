plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Alamat server POS bisa diganti saat build tanpa menyentuh kode:
//   gradle assembleDebug -PposUrl=https://server-lain.contoh.com
// Wajib https: cleartext http diblokir Android (network_security_config
// sudah dicabut sejak server dilayani lewat Tailscale HTTPS).
val posUrl: String = (project.findProperty("posUrl") as String?)
    ?: "https://caffee.echidna-carob.ts.net"

android {
    namespace = "com.arunika.pos"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.arunika.pos"
        // 26 supaya ikon adaptif cukup berupa XML -- tidak perlu aset PNG sama
        // sekali. Samsung S10 (Android 9+) jauh di atas batas ini.
        minSdk = 26
        targetSdk = 34
        versionCode = 5
        versionName = "1.4"
        buildConfigField("String", "POS_URL", "\"$posUrl\"")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core-ktx:1.13.1")
}
