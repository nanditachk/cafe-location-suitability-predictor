import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  static const String baseUrl = "http://10.28.27.220:8000";
  // change if real phone

  static Future<Map<String, dynamic>> predict(
      double lat, double lon) async {

    final response = await http.post(
      Uri.parse("$baseUrl/predict"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({
        "latitude": lat,
        "longitude": lon
      }),
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      throw Exception("API Error");
    }
  }
}