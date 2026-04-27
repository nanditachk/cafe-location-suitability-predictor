import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../services/api_service.dart';

class CafeScreen extends StatefulWidget {
  const CafeScreen({super.key});

  @override
  _CafeScreenState createState() => _CafeScreenState();
}

class _CafeScreenState extends State<CafeScreen> {

  LatLng? selectedLocation;
  double? score;
  List<String> factors = [];
  bool loading = false;

  static final CameraPosition initialPosition = CameraPosition(
    target: LatLng(17.3850, 78.4867),
    zoom: 12,
  );

  void onMapTap(LatLng position) {
    setState(() {
      selectedLocation = position;
    });
  }

  Future<void> analyze() async {
  if (selectedLocation == null) return;

  setState(() {
    loading = true;
    score = null;
    factors = [];
  });

  try {
    final data = await ApiService.predict(
      selectedLocation!.latitude,
      selectedLocation!.longitude,
    );

    print("API RESPONSE: $data");  // 🔥 VERY IMPORTANT

    setState(() {
      score = data["success_score"];
      factors = List<String>.from(data["top_factors"]);
    });

  } catch (e) {
    print("ERROR: $e");  // 🔥 VERY IMPORTANT
  }

  setState(() {
    loading = false;
  });
}

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text("Cafe Suitability")),

      body: Column(
        children: [

          // MAP
          Expanded(
            child: GoogleMap(
              initialCameraPosition: initialPosition,
              onTap: onMapTap,
              markers: selectedLocation == null
                  ? {}
                  : {
                      Marker(
                        markerId: MarkerId("selected"),
                        position: selectedLocation!,
                      )
                    },
            ),
          ),

          // BUTTON
          Padding(
            padding: const EdgeInsets.all(10),
            child: ElevatedButton(
              onPressed: analyze,
              child: Text("Analyze Location"),
            ),
          ),

          // LOADING
          if (loading)
            CircularProgressIndicator(),

          // RESULT
          if (score != null) ...[
            SizedBox(height: 10),

            Text(
              "Score: ${score!.toStringAsFixed(2)}",
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
            ),

            SizedBox(height: 10),

            ...factors.map((f) => Text("• $f")),

            SizedBox(height: 20),
          ]
        ],
      ),
    );
  }
}