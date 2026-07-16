class Shift {
  final int id;
  final String type; // MORNING or NIGHT
  final DateTime startTime;
  final DateTime? endTime;
  final String status; // OPEN or CLOSED
  final int startingCash;
  final int? endingCash;
  final int? expectedEndingCash;
  final int userId;

  Shift({
    required this.id,
    required this.type,
    required this.startTime,
    this.endTime,
    required this.status,
    required this.startingCash,
    this.endingCash,
    this.expectedEndingCash,
    required this.userId,
  });

  factory Shift.fromJson(Map<String, dynamic> json) {
    return Shift(
      id: json['id'],
      type: json['type'],
      startTime: DateTime.parse(json['startTime']),
      endTime: json['endTime'] != null ? DateTime.parse(json['endTime']) : null,
      status: json['status'],
      startingCash: json['startingCash'],
      endingCash: json['endingCash'],
      expectedEndingCash: json['expectedEndingCash'],
      userId: json['userId'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'type': type,
      'startTime': startTime.toIso8601String(),
      'endTime': endTime?.toIso8601String(),
      'status': status,
      'startingCash': startingCash,
      'endingCash': endingCash,
      'expectedEndingCash': expectedEndingCash,
      'userId': userId,
    };
  }
}
