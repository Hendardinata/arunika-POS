import { Router } from 'express';
import { prisma } from '../db';

const router = Router();

// --- QUESTS ---

// GET /api/gamification/quests - Ambil semua quest aktif
router.get('/quests', async (req, res) => {
  try {
    const quests = await prisma.quest.findMany({
      where: { active: true },
    });
    res.json(quests);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch quests' });
  }
});

// POST /api/gamification/quests - Buat quest baru
router.post('/quests', async (req, res) => {
  try {
    const { name, description, targetValue, rewardPoints, rewardXp, type, targetEntityId } = req.body;
    const quest = await prisma.quest.create({
      data: { name, description, targetValue, rewardPoints, rewardXp, type, targetEntityId },
    });
    res.status(201).json(quest);
  } catch (error) {
    res.status(500).json({ error: 'Failed to create quest' });
  }
});

// PUT /api/gamification/quests/:id - Update quest
router.put('/quests/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { name, description, targetValue, rewardPoints, rewardXp, type, targetEntityId } = req.body;
    const quest = await prisma.quest.update({
      where: { id: parseInt(id) },
      data: { name, description, targetValue, rewardPoints, rewardXp, type, targetEntityId },
    });
    res.json(quest);
  } catch (error) {
    res.status(500).json({ error: 'Failed to update quest' });
  }
});

// DELETE /api/gamification/quests/:id - Soft delete quest
router.delete('/quests/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const quest = await prisma.quest.update({
      where: { id: parseInt(id) },
      data: { active: false },
    });
    res.json({ message: 'Quest deleted (soft)', quest });
  } catch (error) {
    res.status(500).json({ error: 'Failed to delete quest' });
  }
});

// --- BADGES ---

// GET /api/gamification/badges - Ambil semua badge
router.get('/badges', async (req, res) => {
  try {
    const badges = await prisma.badge.findMany();
    res.json(badges);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch badges' });
  }
});

// POST /api/gamification/badges - Buat badge baru
router.post('/badges', async (req, res) => {
  try {
    const { name, description, iconUrl, requiredTransactions } = req.body;
    const badge = await prisma.badge.create({
      data: { name, description, iconUrl, requiredTransactions: parseInt(requiredTransactions) || 0 },
    });
    res.status(201).json(badge);
  } catch (error) {
    res.status(500).json({ error: 'Failed to create badge' });
  }
});

// PUT /api/gamification/badges/:id - Update badge
router.put('/badges/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { name, description, iconUrl, requiredTransactions } = req.body;
    const badge = await prisma.badge.update({
      where: { id: parseInt(id) },
      data: { name, description, iconUrl, requiredTransactions: parseInt(requiredTransactions) || 0 },
    });
    res.json(badge);
  } catch (error) {
    res.status(500).json({ error: 'Failed to update badge' });
  }
});

// DELETE /api/gamification/badges/:id - Delete badge
router.delete('/badges/:id', async (req, res) => {
  try {
    const { id } = req.params;
    await prisma.customerBadge.deleteMany({ where: { badgeId: parseInt(id) } });
    const badge = await prisma.badge.delete({
      where: { id: parseInt(id) },
    });
    res.json({ message: 'Badge deleted', badge });
  } catch (error) {
    res.status(500).json({ error: 'Failed to delete badge' });
  }
});

// --- REWARDS ---

// GET /api/gamification/rewards - Ambil semua reward aktif
router.get('/rewards', async (req, res) => {
  try {
    const rewards = await prisma.reward.findMany({
      where: { active: true },
    });
    res.json(rewards);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch rewards' });
  }
});

// POST /api/gamification/rewards - Buat reward baru
router.post('/rewards', async (req, res) => {
  try {
    const { name, description, pointsRequired } = req.body;
    const reward = await prisma.reward.create({
      data: { name, description, pointsRequired },
    });
    res.status(201).json(reward);
  } catch (error) {
    res.status(500).json({ error: 'Failed to create reward' });
  }
});

// PUT /api/gamification/rewards/:id - Update reward
router.put('/rewards/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { name, description, pointsRequired } = req.body;
    const reward = await prisma.reward.update({
      where: { id: parseInt(id) },
      data: { name, description, pointsRequired },
    });
    res.json(reward);
  } catch (error) {
    res.status(500).json({ error: 'Failed to update reward' });
  }
});

// DELETE /api/gamification/rewards/:id - Soft delete reward
router.delete('/rewards/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const reward = await prisma.reward.update({
      where: { id: parseInt(id) },
      data: { active: false },
    });
    res.json({ message: 'Reward deleted (soft)', reward });
  } catch (error) {
    res.status(500).json({ error: 'Failed to delete reward' });
  }
});

// POST /api/gamification/redeem - Tukar poin dengan reward
router.post('/redeem', async (req, res) => {
  try {
    const { customerId, rewardId } = req.body;

    const customer = await prisma.customer.findUnique({ where: { id: customerId } });
    const reward = await prisma.reward.findUnique({ where: { id: rewardId } });

    if (!customer || !reward) {
      return res.status(404).json({ error: 'Customer or Reward not found' });
    }

    if (!reward.active) {
      return res.status(400).json({ error: 'Reward is not active' });
    }

    if (customer.points < reward.pointsRequired) {
      return res.status(400).json({ error: 'Insufficient points' });
    }

    // Kurangi poin
    const updatedCustomer = await prisma.customer.update({
      where: { id: customerId },
      data: { points: customer.points - reward.pointsRequired },
    });

    res.json({ message: 'Redeem successful', customer: updatedCustomer });
  } catch (error) {
    res.status(500).json({ error: 'Failed to redeem reward' });
  }
});

// POST /api/gamification/spin - Lucky Spin
router.post('/spin', async (req, res) => {
  try {
    const { customerId } = req.body;
    const SPIN_COST = 50;

    const customer = await prisma.customer.findUnique({ where: { id: customerId } });
    if (!customer) {
      return res.status(404).json({ error: 'Customer not found' });
    }

    if (customer.points < SPIN_COST) {
      return res.status(400).json({ error: 'Insufficient points for Lucky Spin' });
    }

    // Deduct points
    let updatedCustomer = await prisma.customer.update({
      where: { id: customerId },
      data: { points: customer.points - SPIN_COST },
    });

    // Randomize Reward (Points / XP)
    const rand = Math.random();
    let rewardName = '';
    let bonusPoints = 0;
    let bonusXp = 0;

    if (rand < 0.1) {
      // 10% chance for Jackpot (200 XP)
      rewardName = 'JACKPOT! +200 XP';
      bonusXp = 200;
    } else if (rand < 0.4) {
      // 30% chance for +100 Points
      rewardName = 'LUCKY! +100 Points';
      bonusPoints = 100;
    } else if (rand < 0.8) {
      // 40% chance for +50 Points (Break Even)
      rewardName = 'Balik Modal! +50 Points';
      bonusPoints = 50;
    } else {
      // 20% chance for Zonk
      rewardName = 'Zonk! Coba lagi besok.';
    }

    if (bonusPoints > 0 || bonusXp > 0) {
      updatedCustomer = await prisma.customer.update({
        where: { id: customerId },
        data: {
          points: updatedCustomer.points + bonusPoints,
          xp: updatedCustomer.xp + bonusXp,
        },
      });
    }

    res.json({
      message: 'Spin completed',
      rewardName,
      bonusPoints,
      bonusXp,
      customer: updatedCustomer,
    });
  } catch (error) {
    res.status(500).json({ error: 'Failed to perform lucky spin' });
  }
});

export default router;
