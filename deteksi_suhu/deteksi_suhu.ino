#include <DHT.h>

#define DHTPIN 2     
#define DHTTYPE DHT11 

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(9600);
  dht.begin();
}

void loop() {
  delay(5000); // Kirim data setiap 1 detik
  
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  
  if (isnan(h) || isnan(t)) {
    return;
  }
  
  // Format JSON string untuk dikirim via Serial
  Serial.print("{\"temperature\":");
  Serial.print(t);
  Serial.print(",\"humidity\":");
  Serial.print(h);
  Serial.println("}");
}