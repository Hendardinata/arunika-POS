import express from 'express';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { prisma } from '../db';

const router = express.Router();
const JWT_SECRET = process.env.JWT_SECRET || 'fallback_secret_for_development_only';

// Login Endpoint
router.post('/login', async (req, res) => {
  const { username, password } = req.body;

  try {
    const user = await prisma.user.findUnique({
      where: { username }
    });

    if (!user) {
      res.status(401).json({ error: 'Invalid username or password' });
      return;
    }

    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      res.status(401).json({ error: 'Invalid username or password' });
      return;
    }

    const token = jwt.sign(
      { id: user.id, username: user.username, role: user.role, assignedShift: user.assignedShift },
      JWT_SECRET,
      { expiresIn: '24h' }
    );

    res.json({
      message: 'Login successful',
      token,
      user: {
        id: user.id,
        username: user.username,
        role: user.role,
        assignedShift: user.assignedShift
      }
    });
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Setup/Seed initial user if none exists (for first time run)
router.post('/setup', async (req, res) => {
  try {
    const userCount = await prisma.user.count();
    if (userCount > 0) {
      res.status(400).json({ error: 'Setup already completed. Users exist.' });
      return;
    }

    const salt = await bcrypt.genSalt(10);
    const hashedPassword = await bcrypt.hash('123', salt);

    const user = await prisma.user.create({
      data: {
        username: 'admin',
        password: hashedPassword,
        role: 'OWNER'
      }
    });

    res.status(201).json({ message: 'Initial user admin created successfully' });
  } catch (error) {
    console.error('Setup error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Get all users (Admin/Management)
router.get('/users', async (req, res) => {
  try {
    const users = await prisma.user.findMany({
      select: { id: true, username: true, role: true, assignedShift: true, createdAt: true }
    });
    res.json(users);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch users' });
  }
});

// Create a new user (Admin/Management)
router.post('/users', async (req, res) => {
  const { username, password, role, assignedShift } = req.body;
  if (!username || !password) {
    res.status(400).json({ error: 'Username and password are required' });
    return;
  }
  
  try {
    const existing = await prisma.user.findUnique({ where: { username } });
    if (existing) {
      res.status(400).json({ error: 'Username already exists' });
      return;
    }
    
    const salt = await bcrypt.genSalt(10);
    const hashedPassword = await bcrypt.hash(password, salt);
    
    const user = await prisma.user.create({
      data: {
        username,
        password: hashedPassword,
        role: role || 'CASHIER',
        assignedShift: assignedShift || null
      },
      select: { id: true, username: true, role: true, assignedShift: true, createdAt: true }
    });
    
    res.status(201).json(user);
  } catch (error) {
    res.status(500).json({ error: 'Failed to create user' });
  }
});

// Update a user (Admin/Management)
router.put('/users/:id', async (req, res) => {
  const { username, password, role, assignedShift } = req.body;
  const id = parseInt(req.params.id);
  
  try {
    const existingUser = await prisma.user.findUnique({ where: { id } });
    if (!existingUser) {
      return res.status(404).json({ error: 'User not found' });
    }
    
    const updateData: any = { role, assignedShift: assignedShift || null };
    if (username && username !== existingUser.username) {
      const usernameExists = await prisma.user.findUnique({ where: { username } });
      if (usernameExists) {
        return res.status(400).json({ error: 'Username already exists' });
      }
      updateData.username = username;
    }
    
    if (password && password.trim() !== '') {
      const salt = await bcrypt.genSalt(10);
      updateData.password = await bcrypt.hash(password, salt);
    }
    
    const user = await prisma.user.update({
      where: { id },
      data: updateData,
      select: { id: true, username: true, role: true, assignedShift: true, createdAt: true }
    });
    
    res.json(user);
  } catch (error) {
    res.status(500).json({ error: 'Failed to update user' });
  }
});

// Delete a user
router.delete('/users/:id', async (req, res) => {
  try {
    const id = parseInt(req.params.id);
    
    // Check if user is owner, don't allow deleting the only owner
    const userToDelete = await prisma.user.findUnique({ where: { id } });
    if (!userToDelete) return res.status(404).json({ error: 'User not found' });
    
    const ownerCount = await prisma.user.count({ where: { role: 'OWNER' } });
    if (userToDelete.role === 'OWNER' && ownerCount <= 1) {
      return res.status(400).json({ error: 'Cannot delete the only owner account' });
    }

    // Find another admin or owner to reassign records
    const fallbackUser = await prisma.user.findFirst({
      where: { role: { in: ['OWNER', 'ADMIN'] }, id: { not: id } }
    });

    if (fallbackUser) {
      // Reassign expenses and shifts to prevent deletion of financial history
      await prisma.expense.updateMany({ where: { userId: id }, data: { userId: fallbackUser.id } });
      await prisma.shift.updateMany({ where: { userId: id }, data: { userId: fallbackUser.id } });
    } else {
      // If no fallback user, delete them (edge case)
      await prisma.expense.deleteMany({ where: { userId: id } });
      
      // Before deleting shift, unlink transactions
      const shifts = await prisma.shift.findMany({ where: { userId: id } });
      for (const shift of shifts) {
        await prisma.transaction.updateMany({ where: { shiftId: shift.id }, data: { shiftId: null } });
      }
      await prisma.shift.deleteMany({ where: { userId: id } });
    }

    await prisma.user.delete({ where: { id } });
    res.json({ message: 'User deleted' });
  } catch (error) {
    console.error('Failed to delete user:', error);
    res.status(500).json({ error: 'Failed to delete user' });
  }
});

export default router;
