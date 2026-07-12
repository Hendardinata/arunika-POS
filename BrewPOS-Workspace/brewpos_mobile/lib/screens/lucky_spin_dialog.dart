import 'package:flutter/material.dart';

class LuckySpinDialog extends StatefulWidget {
  final String rewardName;
  final int bonusPoints;
  final int bonusXp;

  const LuckySpinDialog({
    super.key,
    required this.rewardName,
    required this.bonusPoints,
    required this.bonusXp,
  });

  @override
  State<LuckySpinDialog> createState() => _LuckySpinDialogState();
}

class _LuckySpinDialogState extends State<LuckySpinDialog> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  bool _isSpinning = true;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();

    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() {
          _isSpinning = false;
        });
        _controller.stop();
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(32)),
      elevation: 0,
      backgroundColor: Colors.transparent,
      child: Container(
        padding: const EdgeInsets.all(32),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(32),
          boxShadow: [
            BoxShadow(
              color: Colors.amber.withOpacity(0.2),
              blurRadius: 40,
              offset: const Offset(0, 10),
            )
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.amber[50],
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Text(
                'LUCKY SPIN',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: Colors.amber,
                  letterSpacing: 2,
                ),
              ),
            ),
            const SizedBox(height: 32),
            _isSpinning
                ? RotationTransition(
                    turns: _controller,
                    child: Container(
                      width: 120,
                      height: 120,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: Colors.amber[50],
                      ),
                      child: const Icon(Icons.stars_rounded, size: 80, color: Colors.amber),
                    ),
                  )
                : Column(
                    children: [
                      TweenAnimationBuilder<double>(
                        tween: Tween(begin: 0.0, end: 1.0),
                        duration: const Duration(milliseconds: 600),
                        curve: Curves.elasticOut,
                        builder: (context, value, child) {
                          return Transform.scale(
                            scale: value,
                            child: Container(
                              width: 120,
                              height: 120,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: widget.bonusPoints > 0 || widget.bonusXp > 0 ? Colors.amber[50] : Colors.grey[100],
                              ),
                              child: Icon(
                                widget.bonusPoints > 0 || widget.bonusXp > 0 ? Icons.workspace_premium_rounded : Icons.sentiment_dissatisfied_rounded,
                                size: 64,
                                color: widget.bonusPoints > 0 || widget.bonusXp > 0 ? Colors.amber : Colors.grey[400],
                              ),
                            ),
                          );
                        },
                      ),
                      const SizedBox(height: 24),
                      Text(
                        widget.rewardName,
                        style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.bold,
                          color: Colors.brown[900],
                        ),
                        textAlign: TextAlign.center,
                      ),
                      if (widget.bonusPoints > 0 || widget.bonusXp > 0) ...[
                        const SizedBox(height: 8),
                        Text(
                          'Congratulations!',
                          style: TextStyle(
                            fontSize: 16,
                            color: Colors.grey[500],
                          ),
                        ),
                      ]
                    ],
                  ),
            const SizedBox(height: 40),
            SizedBox(
              width: double.infinity,
              height: 56,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.amber,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  elevation: 0,
                ),
                onPressed: _isSpinning ? null : () => Navigator.of(context).pop(),
                child: const Text('Awesome!', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
