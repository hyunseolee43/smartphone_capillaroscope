const int left_en = 2;
const int right_en = 3;
const int lpwm = 5;
const int rpwm = 6;

int motorSpeed = 255;  // Set speed (0-255)
int mode = 0;          //0 = stop, 1 = forward, 2 = reverse

void setup() {
  Serial.begin(9600);  // Initialize serial communication
  pinMode(left_en, OUTPUT);
  pinMode(right_en, OUTPUT);
  pinMode(lpwm, OUTPUT);
  pinMode(rpwm, OUTPUT);
  delay(2000);
  Serial.println("-------------------------------------------------------------------------------------------------------------------------------------");
  Serial.println("Commands: \n   'forward' to run motor forward \n   'reverse' to run motor in reverse \n   'stop' to stop the motor \n   'speed [insert speed 0-100)' to set the motor speed");
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();  // Remove any trailing whitespace

    if (command == "forward") {
      mode = 1;
      Serial.println("Forward motor.");
    } else if (command == "reverse") {
      mode = 2;
      Serial.println("Reverse motor.");
    } else if (command == "stop") {
      mode = 0;
      Serial.println("Motor stopped.");
    } else if (command.startsWith("speed ")) {
      int speed = (int)((command.substring(5).toDouble()/100)*255);
      if (speed >= 0 && speed <= 255) {
        motorSpeed = speed;
        Serial.println("Speed set to" + command.substring(5) + ".");
      } else {
        Serial.println("Invalid speed.");
      }
    }
  }

  if (mode == 1) {
    digitalWrite(left_en, HIGH);
    digitalWrite(right_en, HIGH);
    analogWrite(lpwm, 0);
    analogWrite(rpwm, motorSpeed);  // Constant speed forward
  } else if (mode == 2) {
    digitalWrite(left_en, HIGH);
    digitalWrite(right_en, HIGH);
    analogWrite(lpwm, motorSpeed);  // Constant speed reverse
    analogWrite(rpwm, 0);
  } else if (mode == 0) {
    digitalWrite(left_en, LOW);
    digitalWrite(right_en, LOW);
    analogWrite(lpwm, 0);
    analogWrite(lpwm, 0);  // motor stopped
  }
}
