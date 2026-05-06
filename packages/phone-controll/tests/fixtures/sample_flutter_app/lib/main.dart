import 'package:flutter/material.dart';

void main() {
  runApp(const SampleApp());
}

class SampleApp extends StatelessWidget {
  const SampleApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Sample',
      home: Scaffold(
        appBar: AppBar(title: const Text('Sample')),
        body: const Center(child: Text('Hello, MCP')),
      ),
    );
  }
}
